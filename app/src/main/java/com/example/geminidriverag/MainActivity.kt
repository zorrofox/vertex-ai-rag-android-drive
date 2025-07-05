package com.example.geminidriverag

import android.app.Activity
import android.os.Bundle
import android.util.Log
import android.view.View
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.example.geminidriverag.databinding.ActivityMainBinding
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInAccount
import com.google.android.gms.auth.api.signin.GoogleSignInClient
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.common.api.Scope
import com.google.android.gms.tasks.Task
import com.google.api.services.drive.DriveScopes
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject
import org.json.JSONException
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var googleSignInClient: GoogleSignInClient
    private var isSigningOut = false
    private var accessToken: String? = null

    private val TAG = "MainActivity"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        savedInstanceState?.let {
            isSigningOut = it.getBoolean("isSigningOut", false)
        }

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // 1. Configure sign-in to request the user's ID, email address, and basic
        // profile. ID and basic profile are included in DEFAULT_SIGN_IN.
        val gso = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestEmail()
            .requestScopes(Scope(DriveScopes.DRIVE_READONLY))
            .requestServerAuthCode(getString(R.string.server_client_id), true)
            .build()

        // 2. Build a GoogleSignInClient with the options specified by gso.
        googleSignInClient = GoogleSignIn.getClient(this, gso)

        // 3. Set up button click listeners in updateUI
    }

    override fun onStart() {
        super.onStart()

        if (isSigningOut) {
            isSigningOut = false
            // Skip the sign-in check below because the user just signed out.
            updateUI(null)
            return
        }

        Log.d(TAG, "onStart: Trying to silently sign in.")
        googleSignInClient.silentSignIn().addOnCompleteListener(this) { task ->
            if (task.isSuccessful) {
                Log.d(TAG, "onStart: Silent sign-in successful.")
                val account = task.result
                updateUI(account)
            } else {
                Log.d(TAG, "onStart: Silent sign-in failed. User needs to sign in manually.")
                // If silent sign-in fails, the user needs to sign in manually.
                updateUI(null)
            }
        }
    }

    private val signInLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val task = GoogleSignIn.getSignedInAccountFromIntent(result.data)
            handleSignInResult(task)
        }
    }

    private fun signIn() {
        val signInIntent = googleSignInClient.signInIntent
        signInLauncher.launch(signInIntent)
    }

    private fun signOut() {
        Log.d(TAG, "signOut: button clicked, attempting to revoke access.")
        isSigningOut = true
        googleSignInClient.revokeAccess().addOnCompleteListener(this) { task ->
            if (task.isSuccessful) {
                Log.d(TAG, "signOut: revokeAccess successful.")
                // The onStart() method will handle the UI update.
            } else {
                isSigningOut = false // Reset the flag on failure
                Log.e(TAG, "signOut: revokeAccess failed.", task.exception)
            }
        }
    }

    private fun handleSignInResult(completedTask: Task<GoogleSignInAccount>) {
        try {
            val account = completedTask.getResult(ApiException::class.java)
            // Signed in successfully, show authenticated UI.
            updateUI(account)
        } catch (e: ApiException) {
            // The ApiException status code indicates the detailed failure reason.
            // Please refer to the GoogleSignInStatusCodes class reference for more information.
            Log.w(TAG, "signInResult:failed code=" + e.statusCode)
            updateUI(null)
        }
    }

    private fun updateUI(account: GoogleSignInAccount?) {
        Log.d(TAG, "updateUI: called with account: ${account?.email}")
        if (account != null) {
            binding.statusTextview.text = "Signed in as: ${account.email}"
            binding.authButton.text = "Get Token"
            binding.authButton.isEnabled = false // Disable button initially

            // If we don't have an access token yet, get one.
            if (this.accessToken == null) {
                account.serverAuthCode?.let { sendAuthCodeToBackend(it) }
            } else {
                // If we already have a token, the user can process the file.
                binding.authButton.text = "Process File"
                binding.authButton.isEnabled = true
                binding.authButton.setOnClickListener { processFile() }
            }

        } else {
            this.accessToken = null // Clear access token on sign out
            binding.statusTextview.text = "Signed Out"
            binding.authButton.text = "Sign In with Google"
            binding.authButton.isEnabled = true
            binding.authButton.setOnClickListener { 
                signIn() 
            }
            // Also hide the query UI on sign out
            binding.queryInput.visibility = View.GONE
            binding.queryButton.visibility = View.GONE
        }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        outState.putBoolean("isSigningOut", isSigningOut)
    }

    private fun processFile() {
        if (accessToken == null) {
            Log.e(TAG, "processFile: No access token available.")
            binding.statusTextview.append("\nError: No Access Token")
            return
        }

        val executor = Executors.newSingleThreadExecutor()
        executor.execute {
            var connection: HttpURLConnection? = null
            try {
                val url = URL("https://us-central1-grhuang-02.cloudfunctions.net/process_drive_file")
                connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                connection.connectTimeout = 30000 // 30 seconds
                connection.readTimeout = 30000 // 30 seconds
                connection.doOutput = true

                val jsonObject = JSONObject()
                jsonObject.put("accessToken", this.accessToken)
                jsonObject.put("driveFileId", binding.driveIdInput.text.toString())

                val outputStreamWriter = OutputStreamWriter(connection.outputStream)
                outputStreamWriter.write(jsonObject.toString())
                outputStreamWriter.flush()

                val responseCode = connection.responseCode
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    val reader = BufferedReader(InputStreamReader(connection.inputStream))
                    val response = reader.readText()
                    Log.i(TAG, "File Content: $response")
                    runOnUiThread { 
                        binding.statusTextview.append("\nFile Processed OK!")
                        // Show the query input and button now that processing is done
                        binding.queryInput.visibility = View.VISIBLE
                        binding.queryButton.visibility = View.VISIBLE

                        // Set up the click listener for the new query button
                        binding.queryButton.setOnClickListener {
                            val query = binding.queryInput.text.toString()
                            if (query.isNotBlank()) {
                                queryIndex(query)
                            } else {
                                showResultDialog("Info", "Please enter a question.")
                            }
                        }
                    }
                } else {
                    val errorReader = BufferedReader(InputStreamReader(connection.errorStream))
                    val errorResponse = errorReader.readText()
                    Log.e(TAG, "File Processor Error Response: $errorResponse")
                    runOnUiThread {
                        showResultDialog("File Processing Error", errorResponse)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error processing file", e)
                runOnUiThread {
                    showResultDialog("File Processing Error", e.message ?: "An unknown error occurred.")
                }
            } finally {
                connection?.disconnect()
                executor.shutdown()
            }
        }
    }

    private fun queryIndex(query: String) {
        val executor = Executors.newSingleThreadExecutor()
        executor.execute {
            var connection: HttpURLConnection? = null
            try {
                val url = URL("https://us-central1-grhuang-02.cloudfunctions.net/query_index")
                connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                connection.connectTimeout = 30000 // 30 seconds
                connection.readTimeout = 30000 // 30 seconds
                connection.doOutput = true

                val jsonObject = JSONObject()
                jsonObject.put("query", query)
                jsonObject.put("accessToken", this.accessToken)
                jsonObject.put("driveFileId", binding.driveIdInput.text.toString())

                val outputStreamWriter = OutputStreamWriter(connection.outputStream)
                outputStreamWriter.write(jsonObject.toString())
                outputStreamWriter.flush()

                val responseCode = connection.responseCode
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    val reader = BufferedReader(InputStreamReader(connection.inputStream))
                    val response = reader.readText()
                    Log.i(TAG, "Query Response: $response")
                    runOnUiThread {
                        showResultDialog("Query Result", response)
                    }
                } else {
                    val errorReader = BufferedReader(InputStreamReader(connection.errorStream))
                    val errorResponse = errorReader.readText()
                    Log.e(TAG, "Query Error Response: $errorResponse")
                    runOnUiThread {
                        showResultDialog("Query Error", errorResponse)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error querying index", e)
                runOnUiThread {
                    showResultDialog("Query Error", e.message ?: "An unknown error occurred.")
                }
            } finally {
                connection?.disconnect()
                executor.shutdown()
            }
        }
    }

    private fun showResultDialog(title: String, message: String) {
        val formattedMessage = try {
            val jsonObject = JSONObject(message)
            if (jsonObject.has("results")) {
                val results = jsonObject.getJSONArray("results")
                if (results.length() == 0) {
                    "No relevant document chunks found."
                } else {
                    val stringBuilder = StringBuilder()
                    stringBuilder.append("Found ${results.length()} relevant document chunks:\n\n")
                    for (i in 0 until results.length()) {
                        val result = results.getJSONObject(i)
                        val content = result.getString("content")
                        val distance = result.getDouble("distance")
                        stringBuilder.append("--- Chunk (Distance: ${String.format("%.2f", distance)}) ---\n")
                        stringBuilder.append(content)
                        stringBuilder.append("\n\n")
                    }
                    stringBuilder.toString()
                }
            } else {
                jsonObject.toString(2)
            }
        } catch (e: JSONException) {
            message
        }

        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(formattedMessage)
            .setPositiveButton("OK", null)
            .show()
    }

    private fun sendAuthCodeToBackend(authCode: String) {
        val executor = Executors.newSingleThreadExecutor()
        executor.execute {
            var connection: HttpURLConnection? = null
            try {
                val url = URL("https://us-central1-grhuang-02.cloudfunctions.net/exchange_auth_token")
                connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "POST"
                connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
                connection.connectTimeout = 30000 // 30 seconds
                connection.readTimeout = 30000 // 30 seconds
                connection.doOutput = true

                val jsonObject = JSONObject()
                jsonObject.put("authCode", authCode)

                val outputStreamWriter = OutputStreamWriter(connection.outputStream)
                outputStreamWriter.write(jsonObject.toString())
                outputStreamWriter.flush()

                val responseCode = connection.responseCode
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    val reader = BufferedReader(InputStreamReader(connection.inputStream))
                    val response = reader.readText()
                    val responseJson = JSONObject(response)
                    this.accessToken = responseJson.getString("token")
                    Log.i(TAG, "Access Token acquired: ${this.accessToken}")
                    runOnUiThread {
                        binding.statusTextview.append("\nAccess Token Acquired!")
                        binding.authButton.text = "Process File"
                        binding.authButton.isEnabled = true
                        binding.authButton.setOnClickListener { processFile() }
                    }
                } else {
                    val errorReader = BufferedReader(InputStreamReader(connection.errorStream))
                    val errorResponse = errorReader.readText()
                    Log.e(TAG, "Backend Error Response: $errorResponse")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error sending auth code to backend", e)
            } finally {
                connection?.disconnect()
                executor.shutdown()
            }
        }
    }
}