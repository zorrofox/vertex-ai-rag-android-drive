import functions_framework
import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
import io
import json
import concurrent.futures
import google.cloud.aiplatform as aiplatform
from vertexai.language_models import TextEmbeddingModel
from google.cloud import aiplatform
import docx
import fitz  # PyMuPDF

def decode_text_content(content_bytes):
    """Tries to decode plain text content with a list of common encodings."""
    for encoding in ['utf-8', 'gbk', 'gb2312']:
        try:
            return content_bytes.decode(encoding)
        except UnicodeDecodeError:
            print(f"Failed to decode with {encoding}, trying next...")
    return content_bytes.decode('utf-8', errors='replace')

def extract_text_from_docx(file_stream):
    """Extracts text from a .docx file stream."""
    document = docx.Document(file_stream)
    return "\n".join([para.text for para in document.paragraphs])

def extract_text_from_pdf(file_stream):
    """Extracts text from a .pdf file stream."""
    doc = fitz.open(stream=file_stream, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def chunk_text(text, chunk_size=1000, chunk_overlap=100):
    """Splits the text into chunks of a specified size with overlap."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - chunk_overlap
    return chunks

@functions_framework.http
def process_drive_file(request):
    """HTTP Cloud Function to download, parse, and index a Google Drive file."""
    # CORS headers
    if request.method == 'OPTIONS':
        headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '3600'}
        return ('', 204, headers)
    headers = {'Access-Control-Allow-Origin': '*'}

    request_json = request.get_json(silent=True)
    if not request_json:
        return ('Invalid JSON', 400, headers)

    access_token = request_json.get('accessToken')
    file_id = request_json.get('driveFileId')

    if not access_token or not file_id:
        return ('Missing accessToken or driveFileId', 400, headers)

    try:
        creds = google.oauth2.credentials.Credentials(token=access_token)
        drive_service = build('drive', 'v3', credentials=creds)

        file_metadata = drive_service.files().get(fileId=file_id, fields='mimeType, name').execute()
        mime_type = file_metadata.get('mimeType')
        print(f"Processing file with MIME type: {mime_type}")

        # Download file content
        drive_request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, drive_request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        file_content = ""
        # Parse content based on MIME type
        if mime_type == 'application/pdf':
            file_content = extract_text_from_pdf(fh)
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            file_content = extract_text_from_docx(fh)
        elif 'text' in mime_type or mime_type == 'application/octet-stream':
             # For plain text or unknown binary, try decoding
            file_content_bytes = fh.getvalue()
            file_content = decode_text_content(file_content_bytes)
        else:
            # Fallback for other types like Google Docs, which are exported as text
            export_request = drive_service.files().export_media(fileId=file_id, mimeType='text/plain')
            fh_export = io.BytesIO()
            downloader_export = MediaIoBaseDownload(fh_export, export_request)
            done_export = False
            while not done_export:
                status_export, done_export = downloader_export.next_chunk()
            file_content_bytes = fh_export.getvalue()
            file_content = decode_text_content(file_content_bytes)

        text_chunks = chunk_text(file_content)

        aiplatform.init(project="grhuang-02", location="us-central1")
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        index = aiplatform.MatchingEngineIndex(index_name="5194359011427745792")

        BATCH_SIZE = 25
        
        def process_batch(batch_data):
            i, batch_chunks = batch_data
            try:
                embeddings = model.get_embeddings(batch_chunks)
                datapoints = []
                for j, embedding in enumerate(embeddings):
                    datapoint_index = i + j
                    datapoint = {
                        "datapoint_id": f"{file_id}_{datapoint_index}",
                        "feature_vector": embedding.values,
                        "restricts": [{"namespace": "file_id", "allow_list": [file_id]}]
                    }
                    datapoints.append(datapoint)
                if datapoints:
                    index.upsert_datapoints(datapoints=datapoints)
                    return len(datapoints)
                return 0
            except Exception as e:
                print(f"Error processing batch at index {i}: {e}")
                return 0

        batches = [(i, text_chunks[i:i + BATCH_SIZE]) for i in range(0, len(text_chunks), BATCH_SIZE)]
        total_upserted_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_batch = {executor.submit(process_batch, batch): batch for batch in batches}
            for future in concurrent.futures.as_completed(future_to_batch):
                try:
                    upserted_count = future.result()
                    total_upserted_count += upserted_count
                except Exception as exc:
                    batch_info = future_to_batch[future]
                    print(f'Batch from index {batch_info[0]} generated an exception: {exc}')

        return (json.dumps({"upserted_count": total_upserted_count, "file_type_processed": mime_type}), 200, headers)

    except HttpError as error:
        error_content = error.content.decode('utf-8')
        return (f"An error occurred with the Drive API: {error_content}", 500, headers)
    except Exception as e:
        return (f"An unexpected error occurred: {e}", 500, headers)