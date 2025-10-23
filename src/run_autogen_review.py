import logging
import os
import smtplib
import subprocess
import sys
import time 
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from autogen import AssistantAgent, UserProxyAgent
from fpdf import FPDF
from github import Github

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === 1. CONFIGURATION ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")
COMMIT_SHA = os.getenv("GITHUB_SHA")
GITHUB_ACTOR = os.getenv("GITHUB_ACTOR")

# File size limit (1MB)
MAX_FILE_SIZE = 1024 * 1024

YOUR_CODE_STANDARD_PROMPT = """
Check the code against our company's general coding standards:
1. All functions/methods MUST have clear documentation (docstrings, JSDoc, etc.).
2. Variable names should be clear and follow common conventions for the language (e.g., snake_case for Python, camelCase for JavaScript).
3. No print() or console.log() statements are allowed; use a proper logger.
4. For web components, ensure accessibility (aria-labels, roles) where possible.
"""

# === 2. HELPER FUNCTIONS ===

def get_changed_files(repo_name: str, commit_sha: str, github_token: str) -> List[str]:
    """
    Uses the GitHub API to find all changed files in the specific commit.
    
    Args:
        repo_name: Full repository name (owner/repo)
        commit_sha: Commit SHA to analyze
        github_token: GitHub authentication token
        
    Returns:
        List of changed file paths
    """
    try:
        github_client = Github(github_token)
        repo = github_client.get_repo(repo_name)
        commit = repo.get_commit(commit_sha)

        changed_files = []
        excluded_patterns = ["node_modules/", ".github/", "package-lock.json", "yarn.lock"]
        
        for file in commit.files:
            if any(pattern in file.filename for pattern in excluded_patterns):
                continue
            logger.info(f"Found changed file: {file.filename}")
            changed_files.append(file.filename)
        return changed_files
    except Exception as error:
        logger.error(f"Error getting changed files from GitHub: {error}")
        return []

def run_flake8(file_path: str) -> str:
    """
    Runs flake8 linter on a Python file.
    
    Args:
        file_path: Path to the Python file
        
    Returns:
        Linting results as string
    """
    if not file_path.endswith(".py"):
        return "Error: run_flake8 can only be used on .py files."
    logger.info(f"Running flake8 on {file_path}")
    try:
        result = subprocess.run(
            ["flake8", file_path, "--max-line-length=100"], 
            capture_output=True, 
            text=True, 
            timeout=30
        )
        return f"Flake8 (Python) findings:\n{result.stdout or 'No issues found.'}"
    except subprocess.TimeoutExpired:
        return "Error: Flake8 timed out."
    except FileNotFoundError:
        return "Error: Flake8 not installed."
    except Exception as error:
        return f"Error running flake8: {error}"

def run_eslint(file_path: str) -> str:
    """
    Runs ESLint on JavaScript/TypeScript files.
    
    Args:
        file_path: Path to the JS/TS file
        
    Returns:
        Linting results as string
    """
    if not file_path.endswith((".js", ".jsx", ".ts", ".tsx")):
        return "Error: run_eslint is for .js, .jsx, .ts, or .tsx files."
    logger.info(f"Running ESLint on {file_path}")
    try:
        result = subprocess.run(
            ["npx", "eslint", file_path, "--no-error-on-unmatched-pattern", "--format=compact"], 
            capture_output=True, 
            text=True, 
            timeout=60
        )
        return f"ESLint (JS/TS/React) findings:\n{result.stdout or 'No issues found.'}"
    except subprocess.TimeoutExpired:
        return "Error: ESLint timed out."
    except Exception as error:
        return f"Error running eslint: {error}"

def run_stylelint(file_path: str) -> str:
    """
    Runs Stylelint on CSS/SCSS files.
    
    Args:
        file_path: Path to the CSS/SCSS file
        
    Returns:
        Linting results as string
    """
    if not file_path.endswith((".css", ".scss")):
        return "Error: run_stylelint is for .css or .scss files."
    logger.info(f"Running Stylelint on {file_path}")
    try:
        result = subprocess.run(
            ["npx", "stylelint", file_path, "--allow-empty-input"], 
            capture_output=True, 
            text=True, 
            timeout=60
        )
        return f"Stylelint (CSS/SCSS) findings:\n{result.stdout or 'No issues found.'}"
    except subprocess.TimeoutExpired:
        return "Error: Stylelint timed out."
    except Exception as error:
        return f"Error running stylelint: {error}"

def run_html_validate(file_path: str) -> str:
    """
    Runs html-validate on HTML files.
    
    Args:
        file_path: Path to the HTML file
        
    Returns:
        Validation results as string
    """
    if not file_path.endswith(".html"):
        return "Error: run_html_validate is for .html files."
    logger.info(f"Running html-validate on {file_path}")
    try:
        result = subprocess.run(
            ["npx", "html-validate", file_path], 
            capture_output=True, 
            text=True, 
            timeout=60
        )
        return f"html-validate (HTML) findings:\n{result.stdout or 'No issues found.'}"
    except subprocess.TimeoutExpired:
        return "Error: HTML validation timed out."
    except Exception as error:
        return f"Error running html-validate: {error}"

def create_pdf(report_content: str, filename: str = "report.pdf") -> None:
    """
    Creates a PDF report from the generated text.
    
    Args:
        report_content: Report text content
        filename: Output PDF filename
    """
    logger.info(f"Creating PDF report: {filename}")
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=10)
        # Handle unicode characters better
        safe_content = report_content.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 5, safe_content)
        pdf.output(filename)
        logger.info("PDF report created successfully")
    except Exception as error:
        logger.error(f"Error creating PDF: {error}")

def send_email(to_email: str, subject: str, body: str, attachment_path: str) -> None:
    """
    Sends an email with PDF report attachment via Gmail.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body text
        attachment_path: Path to PDF attachment
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logger.warning("Gmail credentials not found. Skipping email.")
        return
    
    logger.info(f"Preparing to send email to {to_email}")
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    
    try:
        with open(attachment_path, "rb") as attachment_file:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment_file.read())
            encoders.encode_base_64(part)
            part.add_header(
                "Content-Disposition", 
                f"attachment; filename={os.path.basename(attachment_path)}"
            )
            msg.attach(part)
    except Exception as error:
        logger.error(f"Error attaching PDF: {error}")
        return
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, to_email, msg.as_string())
        server.quit()
        logger.info("Email sent successfully")
    except Exception as error:
        logger.error(f"Error sending email: {error}")

def validate_environment() -> bool:
    """
    Validates required environment variables.
    
    Returns:
        True if all required variables are set
    """
    required_vars = {
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "GITHUB_TOKEN": GITHUB_TOKEN,
        "GITHUB_REPOSITORY": REPO_NAME,
        "GITHUB_SHA": COMMIT_SHA,
        "GITHUB_ACTOR": GITHUB_ACTOR
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    
    if missing_vars:
        logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
        return False
    return True

# === 3. MAIN EXECUTION ===
def main():
    """Main execution function."""
    if not validate_environment():
        sys.exit(1)

    # Optimized config for free tier models
    config_list = [
        {
            # Using a reliable free model from OpenRouter
            "model": "meta-llama/llama-3.1-8b-instruct:free",
            "api_key": OPENAI_API_KEY,
            "base_url": "https://openrouter.ai/api/v1",
            # Rate limiting configuration
            "timeout": 120,
            "max_retries": 2
        }
    ]

    # Define AutoGen Agents with optimized prompts
    code_checker = AssistantAgent(
        name="Code_Checker",
        system_message="""You are a code linter dispatcher. Analyze the file extension and call the appropriate tool:
- `.py` → run_flake8(file_path)
- `.js`, `.jsx`, `.ts`, `.tsx` → run_eslint(file_path)
- `.css`, `.scss` → run_stylelint(file_path)
- `.html` → run_html_validate(file_path)

For unsupported file types, respond: "No linter available for this file type."
Call exactly ONE tool based on the file extension.""",
        llm_config={
            "config_list": config_list,
            "cache_seed": None  # Disable caching for free tier
        },
    )

    code_reviewer = AssistantAgent(
        name="Code_Reviewer",
        system_message=f"""You are a code reviewer. Provide concise feedback in two sections:
1. **Optimization Suggestions**: Performance, memory, and readability improvements.
2. **Coding Standards**: Check against these standards:
{YOUR_CODE_STANDARD_PROMPT}

State the language first. Be brief and specific. Skip style issues covered by linters.""",
        llm_config={
            "config_list": config_list,
            "cache_seed": None
        },
    )
    
    user_proxy = UserProxyAgent(
        name="User_Proxy",
        human_input_mode="NEVER",
        code_execution_config=False,
        llm_config=False,
        max_consecutive_auto_reply=1  # Limit conversation turns
    )
    
    user_proxy.register_function(
        function_map={
            "run_flake8": run_flake8,
            "run_eslint": run_eslint,
            "run_stylelint": run_stylelint,
            "run_html_validate": run_html_validate,
        }
    )

    # Run the Review
    logger.info("Starting Multi-Language AutoGen Code Review...")
    changed_files = get_changed_files(REPO_NAME, COMMIT_SHA, GITHUB_TOKEN)

    if not changed_files:
        logger.info("No files changed in this push. Exiting.")
        sys.exit(0)

    full_report_text = f"AutoGen Code Review for commit {COMMIT_SHA[:7]}\nTriggered by: {GITHUB_ACTOR}\n\n"
    language_map = {
        ".py": "Python", ".js": "JavaScript", ".jsx": "React (JSX)",
        ".ts": "TypeScript", ".tsx": "React (TSX)", ".css": "CSS",
        ".scss": "SCSS", ".html": "HTML",
    }

    # Process files with rate limiting awareness
    processed_count = 0
    for file_path in changed_files:
        logger.info(f"Analyzing file: {file_path}")
        full_report_text += f"--- Report for {file_path} ---\n\n"

        file_extension = os.path.splitext(file_path)[1]
        language = language_map.get(file_extension, f"Unknown ({file_extension})")

        # Check file size
        try:
            if os.path.getsize(file_path) > MAX_FILE_SIZE:
                logger.warning(f"File {file_path} exceeds size limit. Skipping.")
                full_report_text += "File too large. Skipped.\n\n"
                continue
        except OSError:
            pass

        # Read file content
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                code_content = file.read()
            if not code_content.strip():
                logger.info("File is empty. Skipping analysis.")
                full_report_text += "File is empty. Skipped.\n\n"
                continue
        except Exception as error:
            logger.error(f"Could not read file {file_path}: {error}")
            full_report_text += f"Error: Could not read file.\n\n"
            continue

        # Task 1: Linter Check
        try:
            lint_task = f"Run the correct linter for: '{file_path}'"
            user_proxy.initiate_chat(code_checker, message=lint_task, clear_history=True)
            linter_report = user_proxy.last_message(code_checker)["content"]
            full_report_text += f"**Linter Check ({language}):**\n{linter_report}\n\n"
        except Exception as error:
            logger.error(f"Linter check failed: {error}")
            full_report_text += f"**Linter Check:** Error occurred\n\n"

        # Task 2: Code Review (only for code files, limit content size)
        if file_extension in language_map:
            try:
                # Truncate large files for review
                truncated_content = code_content[:5000] if len(code_content) > 5000 else code_content
                review_task = f"Review this {language} code for optimizations and standards:\n\n```{language}\n{truncated_content}\n```"
                
                user_proxy.initiate_chat(code_reviewer, message=review_task, clear_history=True)
                review_report = user_proxy.last_message(code_reviewer)["content"]
                full_report_text += f"**Review:**\n{review_report}\n\n"
            except Exception as error:
                logger.error(f"Code review failed: {error}")
                full_report_text += f"**Review:** Error occurred\n\n"

        full_report_text += f"--- End of Report for {file_path} ---\n\n"

        processed_count += 1
        # Rate limiting: only sleep after every 2 files
        if processed_count % 2 == 0 and processed_count < len(changed_files):
            logger.info("Rate limit delay...")
            time.sleep(5)

    # Generate PDF and Send Email
    logger.info("All files analyzed. Generating final report.")
    create_pdf(full_report_text, "report.pdf")

    developer_email = f"{GITHUB_ACTOR}@users.noreply.github.com"
    email_subject = f"Code Review Report for {REPO_NAME}"
    email_body = f"Hi {GITHUB_ACTOR},\n\nAutomated code review for commit {COMMIT_SHA[:7]}.\n\nFull report attached."

    send_email(developer_email, email_subject, email_body, "report.pdf")

    logger.info("AutoGen Code Review process finished.")

if __name__ == "__main__":
    main()