import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()


def get_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


SMTP_HOST: str = get_env("SMTP_HOST")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
SMTP_USER: str = get_env("SMTP_USER")
SMTP_PASS: str = get_env("SMTP_PASS")
FROM_EMAIL: str = get_env("FROM_EMAIL")
APP_BASE_URL: str = get_env("APP_BASE_URL")


print("SMTP_USER =>", SMTP_USER)
print("SMTP_PASS =>", SMTP_PASS)





def send_verification_email(to_email: str, token: str):

    verify_link = f"{APP_BASE_URL}/users/verify-email?token={token}"

    msg = EmailMessage()
    msg["Subject"] = "Verify Your Email"
    msg["From"] = f"Paper Trade <{FROM_EMAIL}>"
    msg["To"] = to_email

    msg.set_content(f"""
Welcome to PaperTrade!

Please verify your email by clicking the link below:

{verify_link}

This link expires in 24 hours.
""")

    msg.add_alternative(f"""
<html>
  <body>
    <h3>Welcome to PaperTrade!</h3>
    <p>Please verify your email by clicking the button below:</p>
    <a href="{verify_link}" 
       style="display:inline-block;padding:10px 20px;
              background-color:#4CAF50;color:white;
              text-decoration:none;border-radius:5px;">
       Verify Email
    </a>
    <p>This link expires in 24 hours.</p>
  </body>
</html>
""", subtype="html")


    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

    except Exception as e:
        print("Email sending failed:", e)
        raise
