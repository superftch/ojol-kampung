from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, get_args
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

ROOT = Path(__file__).resolve().parent.parent
Coin = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Percent = Annotated[int, Field(ge=0, le=100)]
Resource = Literal["fuel", "condition", "data"]
OjolVehicle = Literal["motor", "mobil"]
Need = Literal["makan", "kesehatan", "fisik", "rekreasi", "penampilan", "rumah"]
NEEDS = get_args(Need)


def now():
    return datetime.now(UTC)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class Settings(Model):
    env: Literal["local", "production", "testing"] = "local"
    operator_authorized: bool = False
    runtime_dir: Path = ROOT / ".local"
    threshold: Percent = 60
    resource_reserve_percent: Percent = 20
    max_spend: Coin | None = None
    min_balance: Coin = 20
    max_jobs: int | None = Field(default=None, gt=0)
    max_minutes: int | None = Field(default=None, gt=0)
    idle_poll_seconds: int = Field(default=10, ge=3, le=60)
    telegram_bot_token: SecretStr = Field(default=SecretStr(""), exclude=True, repr=False)
    telegram_chat_id: int | None = Field(default=None, gt=0)
    login_public_url: str = "http://localhost:6080"
    core: Literal["http"] = "http"
    account_name: str = ""
    max_accounts_per_user: int = Field(default=3, ge=1, le=100)
    max_active_workers: int = Field(default=3, ge=1, le=100)
    tunnel_enabled: bool = False
    auto_start: bool = True

    @field_validator("telegram_chat_id", mode="before")
    @classmethod
    def optional_chat_id(cls, value):
        return None if value == "" else value

    @field_validator("login_public_url")
    @classmethod
    def secure_login_origin(cls, value):
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if (
            not parsed.hostname
            or (
                parsed.scheme != "https"
                and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"})
            )
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "URL import cookie wajib origin HTTPS atau HTTP localhost, tanpa credential/path/query"
            )
        return value.rstrip("/")

    @field_validator("max_spend", "max_jobs", "max_minutes", mode="before")
    @classmethod
    def unlimited_spending(cls, value):
        return None if value is None or value == "" else value

    @field_validator("runtime_dir")
    @classmethod
    def absolute_dir(cls, value):
        return (ROOT / value).resolve()

    @model_validator(mode="after")
    def isolate_test(self):
        if self.env == "production":
            if not self.telegram_bot_token.get_secret_value() or not self.telegram_chat_id:
                raise ValueError("Production memerlukan token Telegram dan Chat ID admin pribadi")
            if not self.login_public_url.startswith("https://"):
                raise ValueError("Production memerlukan origin HTTPS untuk Import Cookie")
            if self.min_balance < 20:
                raise ValueError("Saldo minimum production tidak boleh di bawah 20 koin")
        if self.resource_reserve_percent >= self.threshold:
            raise ValueError("Cadangan resource wajib lebih rendah dari threshold")
        if self.env == "testing" and (
            self.operator_authorized or not self.runtime_dir.is_relative_to(ROOT / ".local/testing")
        ):
            raise ValueError("Testing wajib resource lokal khusus dan tidak boleh authorized live")
        if self.env == "testing" and (
            self.tunnel_enabled
            or self.telegram_bot_token.get_secret_value()
            or self.telegram_chat_id
        ):
            raise ValueError("Testing tidak boleh memakai tunnel/Telegram live")
        return self


class GameReceipt(Model):
    id: str = Field(min_length=1)
    done_at: datetime
    kind: str
    origin: str
    destination: str
    amount: Coin


class SleepSchedule(Model):
    auto: bool = Field(strict=True)
    start: int = Field(ge=0, lt=1440, strict=True)
    end: int = Field(ge=0, lt=1440, strict=True)
    in_schedule: bool = Field(strict=True)

    def next_transition(self, server_now):
        if not self.auto:
            return None
        local = server_now.astimezone(ZoneInfo("Asia/Jakarta"))
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        boundaries = [midnight + timedelta(minutes=value) for value in (self.start, self.end)]
        return min(value if value > local else value + timedelta(days=1) for value in boundaries)


class Snapshot(Model):
    observed_at: datetime = Field(default_factory=now)
    wallet: Coin
    fuel: Percent
    condition: Percent
    data: Percent
    phase: Literal["idle", "searching", "delivering", "complete", "sleeping", "unknown"]
    remaining_seconds: int | None = Field(default=None, ge=0)
    trip: str | None = None
    today_income: Coin | None = None
    history: list[str] = Field(default_factory=list)
    buttons: list[str] = Field(default_factory=list)
    raw_text: str = ""
    needs: dict[Need, Percent] = Field(default_factory=dict)
    game_history: list[GameReceipt] = Field(default_factory=list)
    today_count: int | None = Field(default=None, ge=0)
    trip_id: str | None = None
    arrive_at: datetime | None = None
    home_plot: str | None = None
    village: str | None = None
    sleep_schedule: SleepSchedule | None = None
    ojol_vehicle: OjolVehicle | None = None

    def resource_value(self, resource: Resource | Need):
        return self.needs.get(resource) if resource in NEEDS else getattr(self, resource)


class Product(Model):
    name: str
    price: Coin
    effects: dict[Resource | Need, Percent]
    row_text: str
    enabled: bool


class ShopPreview(Model):
    id: str
    plot_id: str
    name: str
    category: str
    distance_squared: Annotated[int, Field(ge=0)]
    products: list[Product]

    @property
    def preferred(self):
        return "akademis.ai" in self.name.casefold()


class PurchasePlan(Model):
    resource: Resource | Need
    product: Product
    quantity: int = Field(gt=0)
    projected_percent: Percent
    total_cost: Coin


class Step(Model):
    action: Literal["wait", "complete", "maintain", "search", "take", "stop"]
    reason: str
    resource: Resource | None = None
    wait_seconds: int = 0
