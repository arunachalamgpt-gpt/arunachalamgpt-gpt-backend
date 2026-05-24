from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_webhook_secret: str = ""

    # Anthropic Claude
    anthropic_api_key: str
    claude_model: str = "claude-sonnet-4-5"

    # Supabase
    supabase_url: str
    supabase_service_key: str

    # App
    admin_phone: str = ""
    environment: str = "development"

    class Config:
        env_file = ".env"

settings = Settings()