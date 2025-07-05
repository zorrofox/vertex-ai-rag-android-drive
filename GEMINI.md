# Gemini RAG Android Project: Technical Documentation

## 1. Project Overview

This project is a fully functional prototype of an Android application that allows users to perform Retrieval-Augmented Generation (RAG) queries on their personal documents stored in Google Drive. It leverages Google Cloud Functions for backend processing and Vertex AI for embedding generation and vector search.

---

## 2. Core Architecture

The project follows a secure client-server architecture:

*   **Android App (Client)**: Responsible for the user interface, handling Google Sign-In (OAuth 2.0) to acquire user credentials, and communicating with the backend.
*   **Backend (Google Cloud Functions)**: A set of serverless functions handling all heavy lifting:
    *   `exchange_auth_token`: Securely exchanges a one-time authorization code from the app for a long-lived access token.
    *   `file_processor`: Downloads the specified file from Google Drive, intelligently parses its content (supporting `.txt`, `.docx`, and `.pdf`), splits it into chunks, generates vector embeddings using the Vertex AI API, and upserts them into a Vertex AI Vector Search index.
    *   `query_handler`: Receives a user's query, generates an embedding for it, searches the Vector Search index for the most relevant document chunks, and returns the results to the app.

### Workflow Diagram

```
[Android App] --(1. User Auth)--> [Google Sign-In]
      |
(2. Send Auth Code)
      |
      v
[exchange_auth_token Function] --(3. Exchange Code)--> [Google Auth]
      |
(4. Return Access Token)
      |
      v
[Android App] --(5. Process File Request)--> [file_processor Function]
      |
(6. Use Token to Download)--> [Google Drive API]
      |
(7. Create & Store Embeddings) --> [Vertex AI APIs]
      |
      v
[Android App] --(8. Send Query)--> [query_handler Function]
      |
(9. Search & Generate) --> [Vertex AI APIs]
      |
      v
(10. Display Answer)
```

---

## 3. Key Design Decisions & Rationale

This section explains the reasoning behind key architectural and security choices.

### 3.1. Security: Dual OAuth Client IDs

*   **Decision**: We use two types of OAuth 2.0 Client IDs: an **Android** type for the client app and a **Web application** type for the backend.
*   **Rationale**: This is a standard, secure industry practice. The Android Client ID verifies the identity of the app itself (via its package name and SHA-1 fingerprint). The Web Client ID, which includes a `client_secret`, is used by the backend to prove its identity to Google when exchanging the `authCode`. This ensures the highly sensitive `client_secret` is never exposed on the client side.

### 3.2. Security: Configuration Management

*   **Decision**: All secrets (API keys, client IDs, client secrets) were removed from source code and are now managed through local, untracked configuration files (`local.properties` and `config.json`).
*   **Rationale**: Hardcoding secrets in source code is a major security risk. By externalizing them, we can safely commit the code to public repositories. The build process is automated to inject these secrets at compile time, ensuring a seamless developer experience without compromising security.

---

## 4. Setup & Deployment Guide

This is a streamlined guide for setting up and deploying the project. It assumes you have a configured Google Cloud project and Android Studio.

### Step 1: Configure Local Secrets

1.  **Backend (`config.json`)**: 
    *   Copy `functions/exchange_auth_token/config.json.example` to `functions/exchange_auth_token/config.json`.
    *   Fill in the `client_id` and `client_secret` from your **Web application** OAuth credential.

2.  **Android (`local.properties`)**:
    *   In the project's root `local.properties` file, add the following, replacing the placeholders with your actual SDK path and **Web application** Client ID:
        ```properties
        sdk.dir=/path/to/your/android/sdk
        WEB_CLIENT_ID="YOUR_WEB_CLIENT_ID"
        ```

### Step 2: Deploy Backend & Frontend

1.  **Deploy Cloud Functions**:
    ```bash
    gcloud functions deploy exchange_auth_token --source functions/exchange_auth_token --trigger-http --runtime python311 --region us-central1 --allow-unauthenticated
    gcloud functions deploy process_drive_file --source functions/file_processor --trigger-http --runtime python311 --region us-central1 --allow-unauthenticated --timeout 540s --memory 1GiB
    gcloud functions deploy query_index --source functions/query_handler --trigger-http --runtime python311 --region us-central1 --allow-unauthenticated --timeout 540s --memory 1GiB
    ```

2.  **Compile and Install Android App**:
    ```bash
    ./gradlew installDebug
    ```

---

## 5. Knowledge Base & Troubleshooting

This section contains a curated list of issues encountered and their resolutions.

### 5.1. Deployment & Environment

*   **Issue**: The `auth_handler` function consistently failed to deploy with a `Container Healthcheck failed` error, even with minimal "Hello, World!" code.
*   **Root Cause**: The name `auth_handler` likely triggered a security policy or naming conflict within the Google Cloud Run environment, especially after the default deployment version was upgraded to Gen 2. 
*   **Solution**: The function was renamed to `exchange_auth_token`. This forced the creation of a completely new, clean underlying service, which deployed successfully. This serves as a key lesson: when facing inexplicable deployment failures on a specific resource, renaming it can be a powerful solution.

*   **Issue**: The Google Sign-In flow returns a "Forbidden: This app has not been verified by Google" error.
*   **Solution**: This is standard Google security behavior. Add your test user's email address to the "Test users" section of the OAuth consent screen in the Google Cloud Console.

### 5.2. Common Runtime Errors

*   **Error**: `(invalid_grant) Bad Request`
    *   **Cause**: The `authCode` is a one-time use token. This error occurs if you try to use it more than once, which often happened during development when restarting the app.
    *   **Solution**: Implement `GoogleSignIn.silentSignIn()` on app start to get a fresh, valid `authCode` for each session.

*   **Error**: `redirect_uri_mismatch`
    *   **Cause**: The `redirect_uri` used in the backend (`http://localhost`) was not listed in the authorized URIs for the Web application client ID in the Google Cloud Console.
    *   **Solution**: Add `http://localhost` to the list of authorized redirect URIs.

*   **Error**: `Scope has changed`
    *   **Cause**: The scopes requested by the Android app did not exactly match the scopes declared by the backend function.
    *   **Solution**: Ensure the `SCOPES` list in the backend function is identical to all scopes requested by the Android client, including those added by default like `openid`, `email`, and `profile`.

### 5.3. Service Configuration

*   **Issue**: `StreamUpdate is not enabled on this Index` when trying to add data to Vertex AI Vector Search.
*   **Solution**: The Vector Search index must be created with the `--index-update-method=STREAM_UPDATE` flag. It is not possible to enable this after creation; the index must be deleted and recreated with the correct flag.

---

## 6. Known Limitations

*   **File Size Limit**: The current synchronous architecture has a practical file size limit of approximately **7MB**. Processing files larger than this may cause the `process_drive_file` function to time out. For larger files, the backend should be refactored into an asynchronous architecture (e.g., using Cloud Pub/Sub).
