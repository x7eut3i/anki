#!/usr/bin/env python3
"""
User management CLI for the Anki Flashcard App.

Since registration is disabled via the web UI, use this script
on the server to create / list / update / delete users.

Usage:
  python manage_users.py add <username> <email> <password> [--admin]
  python manage_users.py list
  python manage_users.py passwd <username> <new_password>
  python manage_users.py delete <username>
  python manage_users.py promote <username>     # make admin
  python manage_users.py demote <username>       # remove admin
"""

import argparse
import sys
from pathlib import Path

# Ensure backend package is importable
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from sqlmodel import Session, select, SQLModel
from app.config import get_settings
from app.database import engine, create_db_and_tables
from app.models.user import User
from app.models.category import Category
from app.auth import hash_password


def cmd_add(args):
    create_db_and_tables()
    with Session(engine) as session:
        existing = session.exec(
            select(User).where(
                (User.username == args.username) | (User.email == args.email)
            )
        ).first()
        if existing:
            print(f"❌ 用户名或邮箱已存在: {existing.username} ({existing.email})")
            sys.exit(1)

        user = User(
            username=args.username,
            email=args.email,
            hashed_password=hash_password(args.password),
            is_admin=args.admin,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        role = "管理员" if user.is_admin else "普通用户"
        print(f"✅ 用户创建成功: {user.username} ({user.email}) [{role}] id={user.id}")

        # Create default decks for the new user
        _create_default_decks(session, user)
        # Create AI config for the new user
        _create_ai_config(session, user)


def _create_default_decks(session: Session, user: User):
    """Create one default deck per category (skip if already exists by name)."""
    from app.models.category import Category, DEFAULT_CATEGORIES
    from app.models.deck import Deck

    categories = session.exec(
        select(Category).order_by(Category.sort_order)
    ).all()
    if not categories:
        # Seed categories first
        for cat_data in DEFAULT_CATEGORIES:
            cat = Category(**cat_data)
            session.add(cat)
        session.commit()
        categories = session.exec(
            select(Category).order_by(Category.sort_order)
        ).all()

    existing_names = set(r for r in session.exec(select(Deck.name)).all())
    created = 0
    for cat in categories:
        deck_name = f"{cat.icon} {cat.name}"
        if deck_name in existing_names:
            continue
        deck = Deck(
            name=deck_name,
            description=cat.description,
            category_id=cat.id,
            is_public=False,
        )
        session.add(deck)
        created += 1
    if created:
        session.commit()
    print(f"  📦 已创建 {created} 个默认牌组 (跳过 {len(categories) - created} 个已存在)")


def _create_ai_config(session: Session, user: User):
    """Create AI config for a user from ai_config.json if available."""
    import json
    from app.models.ai_config import AIConfig

    ai_config_file = Path(__file__).resolve().parent.parent / "ai_config.json"
    if not ai_config_file.is_file():
        return

    try:
        with open(ai_config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("api_key"):
            return
        config = AIConfig(
            user_id=user.id,
            api_base_url=data.get("api_base_url", "https://api.openai.com/v1"),
            api_key=data["api_key"],
            model=data.get("model", "gpt-4o-mini"),
            max_daily_calls=data.get("max_daily_calls", 100),
            is_enabled=True,
        )
        session.add(config)
        session.commit()
        print(f"  🤖 已配置AI (model: {config.model})")
    except Exception as e:
        print(f"  ⚠️  AI配置失败: {e}")


def cmd_list(args):
    create_db_and_tables()
    with Session(engine) as session:
        users = session.exec(select(User).order_by(User.id)).all()
        if not users:
            print("（暂无用户）")
            return
        print(f"{'ID':<5} {'用户名':<20} {'邮箱':<30} {'管理员':<6} {'状态':<6} {'创建时间'}")
        print("-" * 100)
        for u in users:
            admin = "✓" if u.is_admin else ""
            active = "✓" if u.is_active else "✗"
            print(f"{u.id:<5} {u.username:<20} {u.email:<30} {admin:<6} {active:<6} {u.created_at:%Y-%m-%d %H:%M}")


def cmd_passwd(args):
    create_db_and_tables()
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.username == args.username)
        ).first()
        if not user:
            print(f"❌ 用户不存在: {args.username}")
            sys.exit(1)

        user.hashed_password = hash_password(args.new_password)
        session.add(user)
        session.commit()
        print(f"✅ 密码已更新: {user.username}")


def cmd_delete(args):
    create_db_and_tables()
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.username == args.username)
        ).first()
        if not user:
            print(f"❌ 用户不存在: {args.username}")
            sys.exit(1)

        confirm = input(f"确认删除用户 {user.username} (id={user.id})? [y/N] ")
        if confirm.lower() != "y":
            print("已取消")
            return

        session.delete(user)
        session.commit()
        print(f"✅ 用户已删除: {args.username}")


def cmd_promote(args):
    _set_admin(args.username, True)


def cmd_demote(args):
    _set_admin(args.username, False)


def _set_admin(username: str, is_admin: bool):
    create_db_and_tables()
    with Session(engine) as session:
        user = session.exec(
            select(User).where(User.username == username)
        ).first()
        if not user:
            print(f"❌ 用户不存在: {username}")
            sys.exit(1)

        user.is_admin = is_admin
        session.add(user)
        session.commit()
        role = "管理员" if is_admin else "普通用户"
        print(f"✅ {user.username} 已设为{role}")


def main():
    parser = argparse.ArgumentParser(
        description="Anki 用户管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="创建新用户")
    p_add.add_argument("username", help="用户名 (3~50字符)")
    p_add.add_argument("email", help="邮箱")
    p_add.add_argument("password", help="密码 (≥6字符)")
    p_add.add_argument("--admin", action="store_true", help="设为管理员")
    p_add.set_defaults(func=cmd_add)

    # list
    p_list = sub.add_parser("list", help="列出所有用户")
    p_list.set_defaults(func=cmd_list)

    # passwd
    p_pw = sub.add_parser("passwd", help="修改用户密码")
    p_pw.add_argument("username", help="用户名")
    p_pw.add_argument("new_password", help="新密码")
    p_pw.set_defaults(func=cmd_passwd)

    # delete
    p_del = sub.add_parser("delete", help="删除用户")
    p_del.add_argument("username", help="用户名")
    p_del.set_defaults(func=cmd_delete)

    # promote
    p_pro = sub.add_parser("promote", help="提升为管理员")
    p_pro.add_argument("username", help="用户名")
    p_pro.set_defaults(func=cmd_promote)

    # demote
    p_dem = sub.add_parser("demote", help="取消管理员")
    p_dem.add_argument("username", help="用户名")
    p_dem.set_defaults(func=cmd_demote)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
