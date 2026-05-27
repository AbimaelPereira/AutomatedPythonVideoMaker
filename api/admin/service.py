from sqlmodel import Session, select
from auth.models import User, Group
from auth.service import hash_password
from admin.models import Module


# ── Users ──────────────────────────────────────────────────────────────────

def list_users(session: Session):
    return session.exec(select(User)).all()

def get_user(user_id: int, session: Session):
    return session.get(User, user_id)

def create_user(data: dict, session: Session) -> User:
    user = User(**{**data, "password": hash_password(data["password"])})
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

def update_user(user: User, data: dict, session: Session) -> User:
    for k, v in data.items():
        if k == "password":
            v = hash_password(v)
        setattr(user, k, v)
    session.commit()
    session.refresh(user)
    return user

def delete_user(user: User, session: Session):
    session.delete(user)
    session.commit()


# ── Groups ─────────────────────────────────────────────────────────────────

def list_groups(session: Session):
    return session.exec(select(Group)).all()

def get_group(group_id: int, session: Session):
    return session.get(Group, group_id)

def create_group(data: dict, session: Session) -> Group:
    import json
    if isinstance(data.get("permissions"), dict):
        data["permissions"] = json.dumps(data["permissions"])
    group = Group(**data)
    session.add(group)
    session.commit()
    session.refresh(group)
    return group

def update_group(group: Group, data: dict, session: Session) -> Group:
    import json
    for k, v in data.items():
        if k == "permissions" and isinstance(v, dict):
            v = json.dumps(v)
        setattr(group, k, v)
    session.commit()
    session.refresh(group)
    return group

def delete_group(group: Group, session: Session):
    session.delete(group)
    session.commit()


# ── Modules ────────────────────────────────────────────────────────────────

def list_modules(session: Session):
    return session.exec(select(Module)).all()

def list_parent_modules(session: Session):
    return session.exec(select(Module).where(Module.id_parent == None)).all()

def list_visible_modules(id_group: int, permissions_json: str, session: Session):
    import json
    if id_group == 1:
        return session.exec(select(Module).where(Module.show_in_menu == 1)).all()
    perms = json.loads(permissions_json)
    allowed_slugs = [slug for slug, actions in perms.items() if "view" in actions]
    modules = session.exec(select(Module).where(Module.show_in_menu == 1)).all()
    return [m for m in modules if m.slug in allowed_slugs]

def get_module(module_id: int, session: Session):
    return session.get(Module, module_id)

def create_module(data: dict, session: Session) -> Module:
    module = Module(**data)
    session.add(module)
    session.commit()
    session.refresh(module)
    return module

def update_module(module: Module, data: dict, session: Session) -> Module:
    for k, v in data.items():
        setattr(module, k, v)
    session.commit()
    session.refresh(module)
    return module

def delete_module(module: Module, session: Session):
    session.delete(module)
    session.commit()
