import os
import smtplib
import subprocess
import sys
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# IMPORT THE NEW GROUP CHAT CLASSES
from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
from fpdf import FPDF
from github import Github

# === 1. CONFIGURATION ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")
COMMIT_SHA = os.getenv("GITHUB_SHA")
GITHUB_ACTOR = os.getenv("GITHUB_ACTOR")

YOUR_CODE_STANDARD_PROMPT = """
Check the code against our company's general coding standards:
1. All functions/methods MUST have clear documentation (docstrings, JSDoc, etc.).
2. Variable names should be clear and follow common conventions for the language (e.g., snake_case for Python, camelCase for JavaScript).
3. No print() or console.log() statements are allowed; use a proper logger.
4. For web components, ensure accessibility (aria-labels, roles) where possible.
"""

# === 2. HELPER FUNCTIONS ===

def get_changed_files(repo_name, commit_sha, github_token):
    """Uses the GitHub API to find all changed files in the specific commit."""
    try:
        g = Github(auth=Github.Auth.Token(github_token))
        repo = g.get_repo(repo_name)
        commit = repo.get_commit(commit_sha)
        changed_files = []
        for file in commit.files:
            if "node_modules/" in file.filename or ".github/" in file.filename:
                continue
            print(f"Found changed file: {file.filename}")
            changed_files.append(file.filename)
        return changed_files
    except Exception as e:
        print(f"Error getting changed files from GitHub: {e}")
        return []

# --- Tool functions ---
def run_flake8(file_path):
    if not file_path.endswith(".py"): return "Error: run_flake8 is for .py files."
    print(f"--- Running flake8 on {file_path} ---")
    try:
        result = subprocess.run(["flake8", file_path], capture_output=True, text=True, timeout=30)
        return f"Flake8 (Python) findings:\n{result.stdout or 'No issues found.'}"
    except Exception as e: return f"Error running flake8: {e}"

def run_eslint(file_path):
    if not file_path.endswith((".js", ".jsx", ".ts", ".tsx")): return "Error: run_eslint is for .js, .jsx, .ts, or .tsx files."
    print(f"--- Running ESLint on {file_path} ---")
    try:
        result = subprocess.run(["npx", "eslint", file_path, "--no-error-on-unmatched-pattern"], capture_output=True, text=True, timeout=60)
        return f"ESLint (JS/TS/React) findings:\n{result.stdout or 'No issues found.'}"
    except Exception as e: return f"Error running eslint: {e}"

def run_stylelint(file_path):
    if not file_path.endswith((".css", ".scss")): return "Error: run_stylelint is for .css or .scss files."
    print(f"--- Running Stylelint on {file_path} ---")
    try:
        result = subprocess.run(["npx", "stylelint", file_path, "--allow-empty-input"], capture_output=True, text=True, timeout=60)
        return f"Stylelint (CSS/SCSS) findings:\n{result.stdout or 'No issues found.'}"
    except Exception as e: return f"Error running stylelint: {e}"

def run_html_validate(file_path):
    if not file_path.endswith(".html"): return "Error: run_html_validate is for .html files."
    print(f"--- Running html-validate on {file_path} ---")
    try:
        result = subprocess.run(["npx", "html-validate", file_path], capture_output=True, text=True, timeout=60)
        return f"html-validate (HTML) findings:\n{result.stdout or 'No issues found.'}"
    except Exception as e: return f"Error running html-validate: {e}"

# --- PDF and Email functions ---
def create_pdf(report_content, filename="report.pdf"):
    print(f"--- Creating PDF report: {filename} ---")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 5, report_content.encode('latin-1', 'replace').decode('latin-1'))
    pdf.output(filename)
    print("--- PDF report created successfully. ---")

def send_email(to_email, subject, body, attachment_path):
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("Gmail credentials not found. Skipping email.")
        return
    print(f"--- Preparing to send email to {to_email} ---")
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with open(attachment_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        encoders.encode_base_64(part)
        part.add_header("Content-Disposition", f"attachment; filename= {os.path.basename(attachment_path)}")
        msg.attach(part)
    except Exception as e: print(f"Error attaching PDF: {e}")
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        text = msg.as_string()
        server.sendmail(GMAIL_USER, to_email, text)
        server.quit()
        print("--- Email sent successfully. ---")
    except Exception as e: print(f"Error sending email: {e}")

# === 3. MAIN EXECUTION (NEW GROUPCHAT LOGIC) ===
if __name__ == "__main__":
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set.")
        sys.exit(1)

    # Define the LLM config once
    config_list = [
        {
            "model": "mistralai/mistral-small-24b-instruct-2501:free", # Free model
            "api_key": OPENAI_API_KEY,
            "base_url": "https://openrouter.ai/api/v1"
        }
    ]
    llm_config = {"config_list": config_list}

    # --- Define Agents ---
    code_checker = AssistantAgent( name="Code_Checker", system_message="""You are a code linter dispatcher...""", llm_config=llm_config ) # Shortened for brevity
    code_optimizer = AssistantAgent( name="Code_Optimizer", system_message="""You are a senior developer...""", llm_config=llm_config ) # Shortened for brevity
    code_standard_enforcer = AssistantAgent( name="Standard_Enforcer", system_message=f"""You are a tech lead...{YOUR_CODE_STANDARD_PROMPT}...""", llm_config=llm_config ) # Shortened for brevity
    user_proxy = UserProxyAgent( name="User_Proxy", human_input_mode="NEVER", code_execution_config=False, llm_config=False,
        function_map={ "run_flake8": run_flake8, "run_eslint": run_eslint, "run_stylelint": run_stylelint, "run_html_validate": run_html_validate }
    )

    # --- Define the Group Chat ---
    groupchat = GroupChat( agents=[user_proxy, code_checker, code_optimizer, code_standard_enforcer], messages=[], max_round=10 )
    manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)

    # --- Run the Review ---
    print("Starting Multi-Language AutoGen Code Review...")
    changed_files = get_changed_files(REPO_NAME, COMMIT_SHA, GITHUB_TOKEN)
    if not changed_files:
        print("No files changed in this push. Exiting.")
        sys.exit(0)

    full_report_text = f"AutoGen Code Review for commit {COMMIT_SHA[:7]}\nTriggered by: {GITHUB_ACTOR}\n\n"
    language_map = { ".py": "Python", ".js": "JavaScript", ".jsx": "React (JSX)", ".ts": "TypeScript", ".tsx": "React (TSX) / Angular", ".css": "CSS", ".scss": "SCSS", ".html": "HTML" }

    # --- Loop through each changed file ---
    for file_path in changed_files:
        print(f"\n=== Analyzing file: {file_path} ===")
        full_report_text += f"--- Report for {file_path} ---\n\n"

        file_extension = os.path.splitext(file_path)[1]
        language = language_map.get(file_extension, f"Unknown ({file_extension})")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code_content = f.read()
            if not code_content.strip():
                print("File is empty. Skipping analysis.")
                full_report_text += "File is empty. Skipped.\n\n"
                continue
        except Exception as e:
            print(f"Could not read file {file_path}: {e}")
            full_report_text += f"Error: Could not read file.\n\n"
            continue

        # --- THIS IS THE CORRECTED task_message ---
        task_message = f"""
Please review the following file: '{file_path}' (Language: {language})

Here is the code:
```{language}
{code_content}
```
Your tasks are:
1. Use the User Proxy to run appropriate linters based on the file type.
2. Suggest optimizations for performance, readability, and maintainability.
3. Ensure the code adheres to the following coding standards:
{YOUR_CODE_STANDARD_PROMPT}
Provide a structured report including:
- Linter Findings
- Optimization Suggestions
- Coding Standards Compliance
"""

        # --- Run the Group Chat for this file ---
        manager.run(task_message=task_message)

        # --- Collect the report from the last assistant message ---
        for msg in reversed(groupchat.messages):
            if msg["role"] == "assistant":
                file_report = msg["content"]
                break
        else:
            file_report = "No report generated."

        full_report_text += file_report + "\n\n"

        # --- Clear messages for next file ---
        groupchat.messages.clear()