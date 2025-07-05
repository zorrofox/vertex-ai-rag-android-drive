# Gemini RAG 结合安卓与谷歌云端硬盘

> **注意**: 本项目从初始搭建到最终部署和文档编写，完全由 Gemini CLI 开发和管理。

本项目是一个功能完善的安卓应用原型，它允许用户对自己存储在 Google Drive 中的个人文档执行“检索增强生成” (RAG) 查询。项目后端利用了 Google Cloud Functions 进行处理，并借助 Vertex AI 实现文本嵌入的生成和向量搜索。

---

## 从原型到产品：重要的后续步骤

本代码库包含的是一个功能性的技术原型。要将其发展为面向公众的生产级应用，您必须完成几个关键的安全、法律和架构升级。

1.  **Google OAuth 应用验证**: 您必须将您的应用提交给 Google 进行官方的 OAuth 验证。这包括提供隐私政策、服务条款，并为请求的每一个权限提供详细的理由。未经审核的应用会导致用户看到“未验证的应用”警告，这将严重影响用户信任。

2.  **生产级的密钥管理**: 对于线上���用，不应依赖本地配置文件。最佳实践是使用像 **Google Secret Manager** 这样的专用服务来存储您的 `CLIENT_SECRET`。您的云函数应被授予相应的 IAM 权限，在运行时动态且安全地访问这些密钥。

3.  **异步架构**: 当前的同步架构有约 7MB 的文件大小限制，并可能导致长时间的等待。生产级应用必须使用异步架构。这通常意味着使用 **Cloud Pub/Sub** 来处理文件索引任务队列，并使用 **Firebase Cloud Messaging (FCM)** 在处理完成时通知用户。

---

## 架构

本项目遵循安全的客户端-服务器架构：

1.  **安卓应用 (客户端)**: 负责用户界面、处理 Google 登录 (OAuth 2.0) 以获取用户凭证，并与后端进行通信。
2.  **后端 (Google Cloud Functions)**: 一组无服务器函数，负责处理所有核心逻辑：
    *   `exchange_auth_token`: 安全地将来自应用的一次性授权码交换为可长期使用的访问令牌。
    *   `file_processor`: 从 Google Drive 下载指定文件，智能地解析其内容 (支持 `.txt`, `.docx`, 和 `.pdf` 格式)，将其分割成文本块，通过 Vertex AI API 生成向量嵌入，并将其存入 Vertex AI 向量搜索索引中。
    *   `query_handler`: 接收用户的查询，为其生成嵌入，在向量搜索索引中查找最相关的文档块，获取这些块的原始文本内容，并将结果返回给应用。

---

## 功能特性

*   **安全认证**: 使用 Google 登录，实现强大且安全的用户认证。
*   **多格式支持**: 能够解析和理解包括 `.txt`, `.docx`, 和 `.pdf` 在内的多种文件格式。
*   **动态查询**: 允许用户针对其文档提出自定义问题。
*   **内容丰富的查询结果**: 直接显示与用户查询最相关的实际文本片段，而不仅仅是ID。

---

## Google Cloud OAuth 设置指南

这是进行主设置和部署前的必要步骤。您必须在 Google Cloud Console 中正确配置 OAuth，应用才能正常运行。

### 1. 配置 OAuth 同意屏幕

1.  前往 [Google Cloud Console](https://console.cloud.google.com/)。
2.  导航至 **API 与服务 > OAuth 同意屏幕**。
3.  为用户类型选择 **外部**，然后点击 **创建**。
4.  填写所需的应用信息（应用名称、用户支持电子邮箱、开发者联系信息等）。
5.  在 **范围** 页面，点击 **添加或移除范围**。找到并添加 Google Drive API 的范围 (`.../auth/drive.readonly`)。
6.  在 **测试用户** 页面，点击 **+ ADD USERS** 并添加您将用于测试应用的 Google 帐号。这对于在开发过程中绕过“未验证的应用”提示至关重要。

### 2. 创建 OAuth 2.0 客户端 ID

您需要创建两种不同类型的客户端 ID。

#### a) Android 客户端 ID

1.  导航至 **API 与服务 > 凭据**。
2.  点击 **+ 创建凭据** 并选择 **OAuth 客户端 ID**。
3.  从应用类型下拉菜单中选择 **Android**。
4.  输入您的应用的 **软件包名称** (例如, `com.example.geminidriverag`)。
5.  您需要提供一个 **SHA-1 证书指纹**。要获取您的调试版 SHA-1 密钥，请在项目根目录中运行以下命令：
    ```bash
    ./gradlew signingReport
    ```
6.  从 `debug` 变体的输出中复制 SHA-1 指纹并粘贴到表单中。
7.  点击 **创建**。您无需保存此凭据中的任何信息。

#### b) Web 应用客户端 ID

1.  再次导航至 **API 与服务 > 凭据**。
2.  点击 **+ 创建凭据** 并再次选择 **OAuth 客户端 ID**。
3.  从应用类型下拉菜单中选择 **Web 应用**。
4.  为其命名 (例如, "Gemini RAG Backend")。
5.  在 **已获授权的重定向 URI** 下，点击 **+ 添加 URI** 并输入 `http://localhost`。
6.  点击 **创建**。
7.  一个对话框将会出现，显示您的 **客户端 ID** 和 **客户端密钥**。**您必须复制这两个值**，它们将在下一步中使用。

---

## 设置与部署

本指南提供了一个经过优化的流程，用于配置和部署此应用。其核心原则是使用本地且不受版本控制的文件来管理您的密钥，这些密钥随后会被构建和部署过程自动使用。

### 第 1 步：本地配置 (唯一需要手动修改的步骤)

您只需编辑以下两个文件即可完成环境设置。

1.  **安卓应用密钥 (`local.properties`)**
    *   **位置**: `/usr/local/google/home/greghuang/mywork/lenovo-pad-rag/local.properties`
    *   **目的**: 存储 Android SDK 路径和 **Web 应用客户端 ID**。
    *   **操作**: 确保文件包含以下内容，并将占位符替换为您的实际值：
        ```properties
        # Android SDK 路径
        sdk.dir=/path/to/your/android/sdk

        # Google Cloud Web 应用客户端 ID
        WEB_CLIENT_ID="YOUR_WEB_CLIENT_ID"
        ```

2.  **后端密钥 (`config.json`)**
    *   **位置**: `/usr/local/google/home/greghuang/mywork/lenovo-pad-rag/functions/exchange_auth_token/config.json`
    *   **目的**: 为 `exchange_auth_token` 云函数提供完整的凭据。
    *   **操作**: 通过复制 `config.json.example` 来创建此文件，并填入您的 **Web 应用客户端** 的详细信息：
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

### 第 2 步：部署

完成本地配置后，您可以使用 Gemini CLI 或手动执行命令来部署整个应用。

#### 方式 A: 使用 Gemini CLI 进行部署

1.  **部署后端云函数**:
    *   使用以下提示：
        > "请部署所有三个云函数：exchange_auth_token, process_drive_file, 和 query_index。请使用各自对应的源文件目录，并为后两个函数应用必要的内存和超时设置。"

2.  **编译并安装安卓应用**:
    *   使用以下提示：
        > "请使用调试模式编译并安装安卓应用。"

#### 方式 B: 手动部署

1.  **部署后端云函数**:
    ```bash
    # 部署认证处理函数
    gcloud functions deploy exchange_auth_token --source functions/exchange_auth_token --trigger-http --runtime python311 --region us-central1 --allow-unauthenticated

    # 部署文件处理函数
    gcloud functions deploy process_drive_file --source functions/file_processor --trigger-http --runtime python311 --region us-central1 --allow-unauthenticated --timeout 540s --memory 1GiB

    # 部署查询处理函数
    gcloud functions deploy query_index --source functions/query_handler --trigger-http --runtime python311 --region us-central1 --allow-unauthenticated --timeout 540s --memory 1GiB
    ```

2.  **编译并安装安卓应用**:
    ```bash
    ./gradlew installDebug
    ```

---

## 注意事项

*   **文件大小限制**: 当前的同步架构对文件大小有一个约 **7MB** 的实际限制。对于更大的文件，必须将后端重构为异步架构（例如，使用 Pub/Sub）以避免函数超时。
*   **成本**: 请注意，使用 Google Cloud 服务（Vertex AI, Cloud Functions 等）会产生费用。请设置预算和提醒来监控您的开销。
