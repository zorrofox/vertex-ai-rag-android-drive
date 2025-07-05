# Gemini RAG with Google Drive on Android

> **Note**: This entire project, from initial scaffolding to final deployment and documentation, was developed and managed by the Gemini CLI.

This project is a fully functional prototype of an Android application that allows users to perform Retrieval-Augmented Generation (RAG) queries on their personal documents stored in Google Drive. It leverages Google Cloud Functions for backend processing and Vertex AI for embedding generation and vector search.

---

## From Prototype to Production: Important Next Steps

This repository contains a functional technical prototype. To evolve this into a production-ready application for public release, you must address several critical security, legal, and architectural requirements.

1.  **Google OAuth App Verification**: You must submit your app for Google's official OAuth verification. This involves providing a privacy policy, terms of service, and a detailed justification for every permission requested. Without verification, users will see an "unverified app" warning, severely impacting user trust.

2.  **Production-Grade Secret Management**: For a live application, you should not rely on local configuration files. The best practice is to use a dedicated service like **Google Secret Manager** to store your `CLIENT_SECRET` and other sensitive keys. Your Cloud Functions should be granted IAM permissions to access these secrets at runtime.

3.  **Asynchronous Architecture**: The current synchronous design has a file size limit of ~7MB and can lead to long wait times. A production app must use an asynchronous architecture. This typically involves using **Cloud Pub/Sub** to queue file processing jobs and **Firebase Cloud Messaging (FCM)** to notify the user when processing is complete.

---

## Architecture

The project follows a secure client-server architecture:

1.  **Android App (Client)**: Responsible for the user interface, handling Google Sign-In (OAuth 2.0) to acquire user credentials, and communicating with the backend.
2.  **Backend (Google Cloud Functions)**: A set of serverless functions handling all heavy lifting:
    *   `exchange_auth_token`: Securely exchanges a one-time authorization code from the app for a long-lived access token.
    *   `file_processor`: Downloads the specified file from Google Drive, intelligently parses its content (supporting `.txt`, `.docx`, and `.pdf`), splits it into chunks, generates vector embeddings using the Vertex AI API, and upserts them into a Vertex AI Vector Search index.
    *   `query_handler`: Receives a user's query, generates an embedding for it, searches the Vector Search index for the most relevant document chunks, retrieves the original text for those chunks, and returns the results to the app.

---

## Features

*   **Secure Authentication**: Uses Google Sign-In for robust and secure user authentication.
*   **Multi-Format Support**: Capable of parsing and understanding various file formats, including `.txt`, `.docx`, and `.pdf`.
*   **Dynamic Queries**: Allows users to ask custom questions about their documents.
*   **Content-Rich Results**: Displays the actual text snippets most relevant to the user's query, not just IDs.

---

## Google Cloud OAuth Setup

This is a prerequisite for the main setup and deployment. You must configure OAuth correctly in the Google Cloud Console for the application to function.

### 1. Configure the OAuth Consent Screen

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  Navigate to **APIs & Services > OAuth consent screen**.
3.  Choose **External** for the User Type and click **Create**.
4.  Fill in the required app information (app name, user support email, developer contact information).
5.  On the **Scopes** page, click **Add or Remove Scopes**. Find the Google Drive API scope (`.../auth/drive.readonly`) and add it.
6.  On the **Test users** page, click **+ ADD USERS** and add the Google account(s) you will use to test the application. This is crucial to bypass the "unverified app" screen during development.

### 2. Create OAuth 2.0 Client IDs

You need to create two separate Client IDs.

#### a) Android Client ID

1.  Navigate to **APIs & Services > Credentials**.
2.  Click **+ CREATE CREDENTIALS** and select **OAuth client ID**.
3.  Select **Android** from the Application type dropdown.
4.  Enter your application's **Package name** (e.g., `com.example.geminidriverag`).
5.  You need to provide a **SHA-1 certificate fingerprint**. To get your debug SHA-1 key, run the following command in your project's root directory:
    ```bash
    ./gradlew signingReport
    ```
6.  Copy the SHA-1 fingerprint from the `debug` variant and paste it into the form.
7.  Click **Create**. You do not need to save any information from this credential.

#### b) Web Application Client ID

1.  Navigate back to **APIs & Services > Credentials**.
2.  Click **+ CREATE CREDENTIALS** and select **OAuth client ID** again.
3.  Select **Web application** from the Application type dropdown.
4.  Give it a name (e.g., "Gemini RAG Backend").
5.  Under **Authorized redirect URIs**, click **+ ADD URI** and enter `http://localhost`.
6.  Click **Create**.
7.  A dialog will appear showing your **Client ID** and **Client Secret**. **You must copy both of these values.** They will be used in the next step.

---

## Setup and Deployment

This guide provides a streamlined process for configuring and deploying the application. The key principle is to use local, untracked files for your secrets, which are then automatically used by the build and deployment processes.

### Step 1: Local Configuration (The Only Manual Step)

You only need to edit two files to set up your environment.

1.  **Android App Secrets (`local.properties`)**
    *   **Location**: `/usr/local/google/home/greghuang/mywork/lenovo-pad-rag/local.properties`
    *   **Purpose**: Stores the Android SDK path and the **Web Application Client ID**.
    *   **Action**: Ensure the file contains the following, replacing placeholders with your actual values:
        ```properties
        # Android SDK location
        sdk.dir=/path/to/your/android/sdk

        # Google Cloud Web Application Client ID
        WEB_CLIENT_ID="YOUR_WEB_CLIENT_ID"
        ```

2.  **Backend Secrets (`config.json`)**
    *   **Location**: `/usr/local/google/home/greghuang/mywork/lenovo-pad-rag/functions/exchange_auth_token/config.json`
    *   **Purpose**: Provides the full credentials for the `exchange_auth_token` Cloud Function.
    *   **Action**: Create this file by copying `config.json.example` and filling in your **Web Application Client** details:
        ```json
        {
          "web": {
            "client_id": "YOUR_WEB_CLIENT_ID",
            "client_secret": "YOUR_WEB_CLIENT_SECRET",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"]
          }
        }
        ```

### Step 2: Deployment

Once the local configuration is complete, you can deploy the entire stack using either the Gemini CLI or manual commands.

#### Option A: Deployment with Gemini CLI

1.  **Deploy Backend Functions**:
    *   Use the following prompt:
        > "Deploy all three cloud functions: exchange_auth_token, process_drive_file, and query_index. Use the appropriate source directories and apply the necessary memory and timeout settings for the latter two."

2.  **Compile and Install Android App**:
    *   Use the following prompt:
        > "Compile and install the Android application using the debug profile."

#### Option B: Manual Deployment

1.  **Deploy Backend Functions**:
    ```bash
    # Deploy the authentication handler
    gcloud functions deploy exchange_auth_token --source functions/exchange_auth_token --trigger-http --runtime python311 --region us-central1 --allow-unauthenticated

    # Deploy the file processor
    gcloud functions deploy process_drive_file --source functions/file_processor --trigger-http --runtime python311 --region us-central1 --allow-unauthenticated --timeout 540s --memory 1GiB

    # Deploy the query handler
    gcloud functions deploy query_index --source functions/query_handler --trigger-http --runtime python311 --region us-central1 --allow-unauthenticated --timeout 540s --memory 1GiB
    ```

2.  **Compile and Install Android App**:
    ```bash
    ./gradlew installDebug
    ```

---

## Important Notes

*   **File Size Limit**: The current synchronous architecture has a practical file size limit of around **7MB**. For larger files, the backend must be refactored into an asynchronous architecture (e.g., using Pub/Sub) to avoid function timeouts.
*   **Cost**: Be aware that using Google Cloud services (Vertex AI, Cloud Functions, etc.) will incur costs. Set up budgets and alerts to monitor your spending.