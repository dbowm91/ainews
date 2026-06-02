from __future__ import annotations

from extensions import db


class ShareConfig(db.Model):  # type: ignore[name-defined]
    __tablename__ = "share_configs"

    id = db.Column(db.Integer, primary_key=True)
    platform_key = db.Column(db.String(32), unique=True, nullable=False)
    label = db.Column(db.String(64), nullable=False)
    url_template = db.Column(db.String(512), nullable=False)
    icon_name = db.Column(db.String(32), nullable=False)
    active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<ShareConfig {self.platform_key}>"