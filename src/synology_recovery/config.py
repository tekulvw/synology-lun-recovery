"""Configuration management."""

import tomli
from pathlib import Path
from dataclasses import dataclass


@dataclass
class SynologyConfig:
    """Configuration for Synology NAS connection."""
    host: str
    port: int
    username: str
    password: str
    use_ssl: bool = True
    verify_ssl: bool = True

    @classmethod
    def from_file(cls, config_path: Path | str) -> "SynologyConfig":
        """Load configuration from a TOML file."""
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "rb") as f:
            data = tomli.load(f)

        nas_config = data.get("nas", {})
        use_ssl = nas_config.get("use_ssl", True)
        # Default port: 5001 for HTTPS, 5000 for HTTP
        default_port = 5001 if use_ssl else 5000
        return cls(
            host=nas_config.get("host", ""),
            port=nas_config.get("port", default_port),
            username=nas_config.get("username", ""),
            password=nas_config.get("password", ""),
            use_ssl=use_ssl,
            verify_ssl=nas_config.get("verify_ssl", True)
        )

    def validate(self) -> None:
        """Validate that required fields are present."""
        if not self.host:
            raise ValueError("NAS host is required")
        if not self.username:
            raise ValueError("NAS username is required")
        if not self.password:
            raise ValueError("NAS password is required")