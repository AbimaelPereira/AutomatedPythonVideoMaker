import mimetypes
import os

from dotenv import load_dotenv

load_dotenv()

IG_PREFIX = "ig"


def ig_key(slug: str, filename: str) -> str:
    """Key padrão para mídia temporária do Instagram (Lifecycle de 1 dia no bucket)."""
    return f"{IG_PREFIX}/{slug}/{filename}"


class R2:
    """Cloudflare R2 (S3-compatível): upload com URL pública + delete.

    Credenciais via .env: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
    R2_BUCKET, R2_PUBLIC_URL.
    """

    def __init__(self, client=None):
        self.account_id = os.getenv("R2_ACCOUNT_ID")
        self.bucket = os.getenv("R2_BUCKET")
        self.public_url = (os.getenv("R2_PUBLIC_URL") or "").rstrip("/")
        faltando = [k for k, v in {
            "R2_ACCOUNT_ID": self.account_id,
            "R2_ACCESS_KEY_ID": os.getenv("R2_ACCESS_KEY_ID"),
            "R2_SECRET_ACCESS_KEY": os.getenv("R2_SECRET_ACCESS_KEY"),
            "R2_BUCKET": self.bucket,
            "R2_PUBLIC_URL": self.public_url,
        }.items() if not v]
        if faltando:
            raise ValueError(f"Variáveis do R2 ausentes no .env: {', '.join(faltando)}")

        if client is None:
            import boto3
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{self.account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
                region_name="auto",
            )
        self.client = client

    def upload_file(self, path: str, key: str) -> str:
        """Sobe o arquivo (multipart automático) e retorna a URL pública."""
        content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
        self.client.upload_file(path, self.bucket, key, ExtraArgs={"ContentType": content_type})
        return f"{self.public_url}/{key}"

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
