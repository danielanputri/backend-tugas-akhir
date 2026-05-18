import sys
from app.db.database import SessionLocal
from app.crud.crud_user import user as crud_user
from app.schemas.user import UserCreate

def seed_users():
    db = SessionLocal()
    try:
        # 1. Create Admin User
        admin_username = "admin"
        admin_user = crud_user.get_by_username(db, username=admin_username)
        if not admin_user:
            print(f"Creating admin user: {admin_username}...")
            admin_in = UserCreate(
                username=admin_username,
                password="passwordAdmin123",
                role="admin"
            )
            crud_user.create(db, obj_in=admin_in)
            print("Admin user created successfully.")
        else:
            print(f"Admin user '{admin_username}' already exists.")

        # 2. Create manager User
        manager_username = "manager"
        manager_user = crud_user.get_by_username(db, username=manager_username)
        if not manager_user:
            print(f"Creating manager user: {manager_username}...")
            manager_in = UserCreate(
                username=manager_username,
                password="passwordManager123",
                role="manager"
            )
            crud_user.create(db, obj_in=manager_in)
            print("manager user created successfully.")
        else:
            print(f"manager user '{manager_username}' already exists.")

    except Exception as e:
        print(f"Error seeding users: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    seed_users()
