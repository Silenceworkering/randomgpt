from dedlainych.config import Settings


def is_admin(user_id: int, config: Settings) -> bool:
    # DB table is an audit mirror; never grants privileges by itself.
    return user_id in config.admin_ids
