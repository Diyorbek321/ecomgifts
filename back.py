# main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from datetime import datetime
import sqlite3
import os
from contextlib import contextmanager

app = FastAPI(title="Gift Business API", version="1.0.0")

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
DATABASE_URL = "gifts.db"


def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("""
                   CREATE TABLE IF NOT EXISTS products
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       name
                       TEXT
                       NOT
                       NULL,
                       description
                       TEXT,
                       price
                       REAL
                       NOT
                       NULL,
                       image_url
                       TEXT,
                       category
                       TEXT,
                       is_available
                       BOOLEAN
                       DEFAULT
                       TRUE,
                       created_at
                       TIMESTAMP
                       DEFAULT
                       CURRENT_TIMESTAMP,
                       telegram_message_id
                       INTEGER
                   )
                   """)

    conn.commit()
    conn.close()


@contextmanager
def get_db():
    """Database connection context manager"""
    conn = sqlite3.connect(DATABASE_URL)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# Pydantic models
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: int
    image_url: Optional[str] = None
    category: Optional[str] = None
    is_available: bool = True


class ProductCreate(ProductBase):
    telegram_message_id: Optional[int] = None


class Product(ProductBase):
    id: int
    created_at: datetime
    telegram_message_id: Optional[int] = None

    class Config:
        from_attributes = True


class TelegramConfig(BaseModel):
    channel_url: str
    bot_token: Optional[str] = None


# Configuration
TELEGRAM_CHANNEL_URL = "https://t.me/your_gift_channel"  # Replace with your actual channel


# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()


# API Endpoints

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Gift Business API",
        "version": "1.0.0",
        "telegram_channel": TELEGRAM_CHANNEL_URL
    }


@app.get("/products/", response_model=List[Product])
async def get_products(
        category: Optional[str] = None,
        available_only: bool = True
):
    """Get all products with optional filtering"""
    with get_db() as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM products WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        if available_only:
            query += " AND is_available = TRUE"

        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        return [dict(row) for row in rows]


@app.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: int):
    """Get a specific product by ID"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Product not found")

        return dict(row)


@app.post("/products/", response_model=Product)
async def create_product(product: ProductCreate):
    """Create a new product (typically called by Telegram bot)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT INTO products (name, description, price, image_url, category, is_available,
                                             telegram_message_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       """, (
                           product.name,
                           product.description,
                           product.price,
                           product.image_url,
                           product.category,
                           product.is_available,
                           product.telegram_message_id
                       ))

        product_id = cursor.lastrowid
        conn.commit()

        # Get the created product
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()

        return dict(row)


@app.put("/products/{product_id}", response_model=Product)
async def update_product(product_id: int, product: ProductBase):
    """Update an existing product"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       UPDATE products
                       SET name         = ?,
                           description  = ?,
                           price        = ?,
                           image_url    = ?,
                           category     = ?,
                           is_available = ?
                       WHERE id = ?
                       """, (
                           product.name,
                           product.description,
                           product.price,
                           product.image_url,
                           product.category,
                           product.is_available,
                           product_id
                       ))

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found")

        conn.commit()

        # Get the updated product
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()

        return dict(row)


@app.delete("/products/{product_id}")
async def delete_product(product_id: int):
    """Delete a product"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found")

        conn.commit()

        return {"message": "Product deleted successfully"}


@app.get("/categories/")
async def get_categories():
    """Get all available product categories"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL")
        rows = cursor.fetchall()

        return [row[0] for row in rows if row[0]]


@app.get("/order/{product_id}")
async def order_product(product_id: int):
    """Get order information (redirects to Telegram channel)"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM products WHERE id = ? AND is_available = TRUE", (product_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Product not found or not available")

        product_name = row[0]

        return {
            "product_id": product_id,
            "product_name": product_name,
            "telegram_channel": 'https://t.me/amoragifts',
            "message": f"To order '{product_name}', please visit our Telegram channel",
            "order_instructions": "Click the link above to go to our Telegram channel and place your order"
        }


@app.get("/config/telegram")
async def get_telegram_config():
    """Get Telegram configuration"""
    return {
        "channel_url": TELEGRAM_CHANNEL_URL,
        "message": "Visit our Telegram channel to place orders"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
