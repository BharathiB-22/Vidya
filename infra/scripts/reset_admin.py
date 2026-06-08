from sqlalchemy import create_engine, text
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = "postgresql://vidya:vidya_dev@localhost:5432/vidya"

engine = create_engine(DATABASE_URL)

new_password = "Admin@123"
hashed = pwd_context.hash(new_password)

with engine.begin() as conn:
    conn.execute(
        text("""
            UPDATE public.platform_users
            SET password_hash = :password_hash
            WHERE email = 'admin@vidya.com'
        """),
        {"password_hash": hashed}
    )

print("Password reset successful!")
print("Email: admin@vidya.com")
print("Password: Admin@123")