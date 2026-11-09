"""统计条目的展示字段。未知 ID 保留，缺失的图鉴信息为 None。"""

from pydantic import BaseModel


class Bf6NamedItem(BaseModel):
    id: str
    name: str | None = None
    image: str | None = None
