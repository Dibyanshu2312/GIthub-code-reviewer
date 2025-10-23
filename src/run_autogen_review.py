import os
import smtplib
import subprocess
import sys
import time 
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from autogen import AssistantAgent, UserProxyAgent, config_list_from_models
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

# *** THIS IS YOUR CUSTOM PROMPT ***
YOUR_CODE_STANDARD_PROMPT = """
Check the code against our company's general coding standards:
1. All functions/methods MUST have clear documentation (docstrings, JSDoc, etc.).
2. Variable names should be clear and follow common conventions for the language (e.g., snake_case for Python, camelCase for JavaScript).
3. No print() or console.log() statements are allowed; use a proper logger.
4. For web components, ensure accessibility (aria-labels, roles) where possible.
"""

# === 2. HELPER FUNCTIONS ===
# ... (All your helper functions: get_changed_files, run_flake8, run_eslint, etc. remain exactly the same) ...

def get_changed_files(repo_name, commit_sha, github_token):
    """Uses the GitHub API to find all changed files in the specific commit."""
    try:
        g = Github(github_token)
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

def run_flake8(file_path):
    """A tool function that runs flake8 on a Python file (.py)."""
    if not file_path.endswith(".py"):
        return "Error: run_flake8 can only be used on .py files."
    print(f"--- Running flake8 on {file_path} ---")
    try:
        result = subprocess.run(
            ["flake8", file_path], capture_output=True, text=True, timeout=30
        )
        return f"Flake8 (Python) findings:\n{result.stdout or 'No issues found.'}"
    except Exception as e:
        return f"Error running flake8: {e}"

def run_eslint(file_path):
    """A tool function that runs ESLint on JS/TS/React/Angular files."""

    if not file_path.endswith((".js", ".jsx", ".ts", ".tsx")):
        return "Error: run_eslint is for .js, .jsx, .ts, or .tsx files."
    print(f"--- Running ESLint on {file_path} ---")
    try:
        result = subprocess.run(
            ["npx", "eslint", file_path, "--no-error-on-unmatched-pattern"], 
            capture_output=True, text=True, timeout=60
        )
        return f"ESLint (JS/TS/React) findings:\n{result.stdout or 'No issues found.'}"
    except Exception as e:
        return f"Error running eslint: {e}"

def run_stylelint(file_path):
    """A tool function that runs Stylelint on CSS/SCSS files."""
    if not file_path.endswith((".css", ".scss")):
        return "Error: run_stylelint is for .css or .scss files."
    print(f"--- Running Stylelint on {file_path} ---")
    try:
        result = subprocess.run(
            ["npx", "stylelint", file_path, "--allow-empty-input"], 
            capture_output=True, text=True, timeout=60
        )
        return f"Stylelint (CSS/SCSS) findings:\n{result.stdout or 'No issues found.'}"
    except Exception as e:
        return f"Error running stylelint: {e}"

def run_html_validate(file_path):
    """A tool function that runs html-validate on HTML files."""
    if not file_path.endswith(".html"):
        return "Error: run_html_validate is for .html files."
    print(f"--- Running html-validate on {file_path} ---")
    try:
        result = subprocess.run(
            ["npx", "html-validate", file_path], 
            capture_output=True, text=True, timeout=60
        )
        return f"html-validate (HTML) findings:\n{result.stdout or 'No issues found.'}"
    except Exception as e:
        return f"Error running html-validate: {e}"

def create_pdf(report_content, filename="report.pdf"):
    """Creates a simple PDF report from the generated text."""
    print(f"--- Creating PDF report: {filename} ---")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 5, report_content.encode('latin-1', 'replace').decode('latin-1'))
    pdf.output(filename)
    print("--- PDF report created successfully. ---")

def send_email(to_email, subject, body, attachment_path):
    """Logs into Gmail and sends an email with the PDF report."""
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
    except Exception as e:
        print(f"Error attaching PDF: {e}")
        return
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        text = msg.as_string()
        server.sendmail(GMAIL_USER, to_email, text)
        server.quit()
        print("--- Email sent successfully. ---")
    except Exception as e:
        print(f"Error sending email: {e}")

# === 3. MAIN EXECUTION ===
# === 3. MAIN EXECUTION ===
if __name__ == "__main__":
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY environment variable not set.")
        sys.exit(1)

    # This tells AutoGen to use the OpenRouter URL
    config_list = [
        {
            # --- THIS IS THE CHANGE ---
            # Using a model known for reliable tool-calling
            
            "model": "openai/gpt-4o-mini",
            
            # Or you could try Claude Haiku:
            # "model": "anthropic/claude-3-haiku-20240307",

            "api_key": OPENAI_API_KEY,
            "base_url": "https://openrouter.ai/api/v1"
        }
    ]

    # --- Define AutoGen Agents ---
    
    # (Rest of your script is exactly the same...)
    # --- Define AutoGen Agents ---

    code_checker = AssistantAgent(
        name="Code_Checker",
        system_message="""You are a code linter dispatcher. Your job is to check for bugs and syntax errors using the correct tool.
You have these tools available:
- `run_flake8(file_path)`: For Python files (.py).
- `run_eslint(file_path)`: For JavaScript/TypeScript files (.js, .jsx, .ts, .tsx).
- `run_stylelint(file_path)`: For stylesheet files (.css, .scss).
- `run_html_validate(file_path)`: For HTML files (.html).
When given a file path, choose the ONE correct tool, call it, and report the findings.
If you do NOT have a tool (e.g., .md, .json), state: "No linter available for this file type."
""",
        llm_config={"config_list": config_list},
    )

    # <-- MODIFICATION: COMBINED AGENT -->
    # We combine the Optimizer and Standard Enforcer into one agent
    code_reviewer = AssistantAgent(
        name="Code_Reviewer",
        system_message=f"""You are a senior developer and tech lead. 
Your job is to review code for two things:
1.  **Optimizations:** Suggest improvements for performance, memory, and readability.
2.  **Coding Standards:** Check the code against our company standards.

**State the language/framework you are reviewing** first.
Then, provide your feedback in two clear sections: "Optimization Suggestions" and "Coding Standards Check".
Do not comment on style issues a linter would find (like commas, spacing).

Our Coding Standards:
{YOUR_CODE_STANDARD_PROMPT}
""",
        llm_config={"config_list": config_list},
    )
    
    # <-- We no longer need code_optimizer or code_standard_enforcer -->

    user_proxy = UserProxyAgent(
        name="User_Proxy",
        human_input_mode="NEVER",
        code_execution_config=False,
        llm_config=False,
    )
    user_proxy.register_function(
        function_map={
            "run_flake8": run_flake8,
            "run_eslint": run_eslint,
            "run_stylelint": run_stylelint,
            "run_html_validate": run_html_validate,
        }
    )

    # --- Run the Review ---
    print("Starting Multi-Language AutoGen Code Review...")
    changed_files = get_changed_files(REPO_NAME, COMMIT_SHA, GITHUB_TOKEN) 

    if not changed_files:
        print("No files changed in this push. Exiting.")
        sys.exit(0)

    full_report_text = f"AutoGen Code Review for commit {COMMIT_SHA[:7]}\nTriggered by: {GITHUB_ACTOR}\n\n"
    language_map = {
        ".py": "Python", ".js": "JavaScript", ".jsx": "React (JSX)",
        ".ts": "TypeScript", ".tsx": "React (TSX) / Angular", ".css": "CSS",
        ".scss": "SCSS", ".html": "HTML",
    }

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

        # Task 1: Run the Code Checker Agent (Same as before)
        lint_task = f"Please run the correct linter for the file: '{file_path}'."
        user_proxy.initiate_chat(code_checker, message=lint_task, clear_history=True)
        linter_report = user_proxy.last_message(code_checker)["content"]
        full_report_text += f"**Linter/Bug Check ({language}):**\n{linter_report}\n\n"

        # <-- MODIFICATION: CALL THE COMBINED AGENT -->
        # Task 2 & 3 are now one call
        review_task = f"Here is the code from '{file_path}' (Language: {language}). Please review it for optimizations and standards:\n\n```{language}\n{code_content}\n```"
        
        user_proxy.initiate_chat(code_reviewer, message=review_task, clear_history=True)
        
        review_report = user_proxy.last_message(code_reviewer)["content"]
        full_report_text += f"**Optimization & Standards Review:**\n{review_report}\n\n" # The report will contain both sections

        full_report_text += f"--- End of Report for {file_path} ---\n\n"

        # We still keep the delay, just in case of "requests per minute" limits
        print("Waiting 10 seconds to avoid rate limits...")
        time.sleep(10) 

    # --- 4. Generate PDF and Send Email ---

    print("\n=== All files analyzed. Generating final report. ===")
    create_pdf(full_report_text, "report.pdf")

    developer_email = f"{GITHUB_ACTOR}@users.noreply.github.com" 
    email_subject = f"Code Review Report for {REPO_NAME}"
    email_body = f"Hi {GITHUB_ACTOR},\n\nHere is the automated code review report for your recent push ({COMMIT_SHA[:7]}).\n\nPlease find the full report attached."

    send_email(developer_email, email_subject, email_body, "report.pdf")

    print("=== AutoGen Code Review process finished. ===")