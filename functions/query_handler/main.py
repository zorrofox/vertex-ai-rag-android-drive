import functions_framework
import json
import google.cloud.aiplatform as aiplatform
from vertexai.language_models import TextEmbeddingModel
import google.oauth2.credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
import io
import docx
import fitz  # PyMuPDF

PROJECT_ID = "grhuang-02"
LOCATION = "us-central1"
INDEX_ENDPOINT_ID = "5556494161152049152"
DEPLOYED_INDEX_ID = "rag_drive_deployed_index_stream"

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
def query_index(request):
    """HTTP Cloud Function to query the Vector Search index and return content."""
    # CORS headers
    if request.method == 'OPTIONS':
        headers = {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'POST', 'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Max-Age': '3600'}
        return ('', 204, headers)
    headers = {'Access-Control-Allow-Origin': '*'}

    request_json = request.get_json(silent=True)
    if not request_json:
        return ('Invalid JSON', 400, headers)

    query_text = request_json.get('query')
    access_token = request_json.get('accessToken')
    file_id = request_json.get('driveFileId')

    if not all([query_text, access_token, file_id]):
        return ('Missing one or more required parameters: query, accessToken, driveFileId', 400, headers)

    try:
        creds = google.oauth2.credentials.Credentials(token=access_token)
        drive_service = build('drive', 'v3', credentials=creds)

        file_metadata = drive_service.files().get(fileId=file_id, fields='mimeType, name').execute()
        mime_type = file_metadata.get('mimeType')
        print(f"Querying file with MIME type: {mime_type}")

        drive_request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, drive_request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        file_content = ""
        if mime_type == 'application/pdf':
            file_content = extract_text_from_pdf(fh)
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            file_content = extract_text_from_docx(fh)
        elif 'text' in mime_type or mime_type == 'application/octet-stream':
            file_content_bytes = fh.getvalue()
            file_content = decode_text_content(file_content_bytes)
        else:
            export_request = drive_service.files().export_media(fileId=file_id, mimeType='text/plain')
            fh_export = io.BytesIO()
            downloader_export = MediaIoBaseDownload(fh_export, export_request)
            done_export = False
            while not done_export:
                status_export, done_export = downloader_export.next_chunk()
            file_content_bytes = fh_export.getvalue()
            file_content = decode_text_content(file_content_bytes)

        text_chunks = chunk_text(file_content)

        aiplatform.init(project=PROJECT_ID, location=LOCATION)
        model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        query_embedding = model.get_embeddings([query_text])[0].values

        index_endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=INDEX_ENDPOINT_ID)

        neighbors = index_endpoint.find_neighbors(
            deployed_index_id=DEPLOYED_INDEX_ID,
            queries=[query_embedding],
            num_neighbors=5
        )

        results = []
        for neighbor in neighbors[0]:
            try:
                chunk_index_str = neighbor.id.split(f"{file_id}_")[-1]
                chunk_index = int(chunk_index_str)
                if 0 <= chunk_index < len(text_chunks):
                    results.append({
                        "id": neighbor.id,
                        "content": text_chunks[chunk_index],
                        "distance": neighbor.distance
                    })
            except (ValueError, IndexError) as e:
                print(f"Could not parse or find chunk for neighbor ID: {neighbor.id}. Error: {e}")

        return (json.dumps({"results": results}), 200, headers)

    except HttpError as error:
        error_content = error.content.decode('utf-8')
        return (f"An error occurred with the Drive API: {error_content}", 500, headers)
    except Exception as e:
        return (f"An unexpected error occurred: {e}", 500, headers)