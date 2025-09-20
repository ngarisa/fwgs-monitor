#!/usr/bin/env python3
"""
Ultra-fast checkout webhook server.
Single-purpose lightweight server that accepts HTTP requests to trigger instant checkout.
Designed for speed - checkout starts in <1 second from notification click.
"""

import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Optional
import json

from . import config, db, autocheckout
from .scraper import Product

logger = logging.getLogger(__name__)

class FastCheckoutHandler(BaseHTTPRequestHandler):
    """Ultra-lightweight HTTP handler for instant checkout triggers."""
    
    def log_message(self, format, *args):
        """Override to use Python logging instead of stderr."""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests for checkout triggers."""
        try:
            # Parse URL and query parameters
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            
            if parsed.path == "/checkout":
                product_id = params.get('id', [None])[0]
                if product_id:
                    success = self._trigger_checkout(product_id)
                    self._send_response(success, product_id)
                else:
                    self._send_error("Missing product ID")
                    
            elif parsed.path == "/checkout-url":
                product_url = params.get('url', [None])[0]
                if product_url:
                    success = self._trigger_checkout_by_url(product_url)
                    self._send_response(success, f"URL: {product_url}")
                else:
                    self._send_error("Missing product URL")
                    
            elif parsed.path == "/status":
                self._send_status()
                
            elif parsed.path == "/" or parsed.path == "/health":
                self._send_health()
                
            else:
                self._send_404()
                
        except Exception as e:
            logger.exception("Error handling request")
            self._send_error(f"Server error: {str(e)}")
    
    def _trigger_checkout(self, product_id: str) -> bool:
        """Trigger checkout for a specific product ID."""
        logger.info("🚀 Fast checkout requested for product ID: %s", product_id)
        
        # Get product from database
        products = db.get_all_products()
        product = products.get(product_id)
        
        if not product:
            logger.warning("Product %s not found in database", product_id)
            return False
        
        # Trigger manual checkout immediately
        success = autocheckout.try_manual_checkout(product, force=True)
        
        if success:
            logger.info("✅ Fast checkout started for %s (%s)", product.name, product_id)
        else:
            logger.warning("❌ Fast checkout failed for %s", product_id)
            
        return success
    
    def _trigger_checkout_by_url(self, product_url: str) -> bool:
        """Trigger checkout for a specific product URL."""
        logger.info("🚀 Fast checkout requested for URL: %s", product_url)
        
        # Create minimal product object for URL-based checkout
        product = Product(
            id="fast_url_checkout",
            name="Fast URL Checkout",
            price=0.0,
            image_url="",
            page_url=product_url,
            quantity=1
        )
        
        success = autocheckout.try_manual_checkout(product, force=True)
        
        if success:
            logger.info("✅ Fast URL checkout started for %s", product_url)
        else:
            logger.warning("❌ Fast URL checkout failed for %s", product_url)
            
        return success
    
    def _send_response(self, success: bool, product_info: str):
        """Send minimal response and close immediately."""
        if success:
            # Send 204 No Content - triggers checkout but no page display
            self.send_response(204)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            logger.info("✅ Fast checkout triggered for %s - minimal response sent", product_info)
        else:
            # Send minimal error response
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Checkout failed: {product_info}".encode())
            logger.warning("❌ Fast checkout failed for %s", product_info)
    
    def _send_error(self, message: str):
        """Send error response."""
        html = f"""
        <html><head><title>Error</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1 style="color: red;">❌ Error</h1>
            <p>{message}</p>
        </body></html>
        """
        self.send_response(400)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def _send_status(self):
        """Send server status as JSON."""
        try:
            products = db.get_all_products()
            available_count = sum(1 for p in products.values() if p.quantity and p.quantity > 0)
            
            status = {
                "status": "running",
                "total_products": len(products),
                "available_products": available_count,
                "auto_checkout_enabled": config.AUTO_CHECKOUT_ENABLED,
                "timestamp": time.time()
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
            
        except Exception as e:
            self._send_error(f"Status error: {str(e)}")
    
    def _send_health(self):
        """Send simple health check."""
        html = """
        <html><head><title>Fast Checkout Server</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1 style="color: green;">🚀 Fast Checkout Server</h1>
            <p>Server is running and ready for instant checkout requests.</p>
            <p><strong>Endpoints:</strong></p>
            <ul style="text-align: left; display: inline-block;">
                <li><code>/checkout?id=PRODUCT_ID</code> - Checkout by product ID</li>
                <li><code>/checkout-url?url=PRODUCT_URL</code> - Checkout by product URL</li>
                <li><code>/status</code> - Server status (JSON)</li>
                <li><code>/health</code> - This page</li>
            </ul>
        </body></html>
        """
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def _send_404(self):
        """Send 404 response."""
        self.send_response(404)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<h1>404 Not Found</h1>")


class FastCheckoutServer:
    """Ultra-lightweight server for instant checkout triggers."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8888):
        self.host = host
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.running = False
    
    def start(self) -> str:
        """Start the server and return the base URL."""
        if self.running:
            return f"http://{self.host}:{self.port}"
        
        try:
            self.server = HTTPServer((self.host, self.port), FastCheckoutHandler)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            self.running = True
            
            base_url = f"http://{self.host}:{self.port}"
            logger.info("🚀 Fast checkout server started at %s", base_url)
            logger.info("   Checkout links will be: %s/checkout?id=PRODUCT_ID", base_url)
            return base_url
            
        except Exception as e:
            logger.error("Failed to start fast checkout server: %s", e)
            return ""
    
    def stop(self):
        """Stop the server."""
        if self.server and self.running:
            self.server.shutdown()
            self.server.server_close()
            self.running = False
            logger.info("Fast checkout server stopped")
    
    def get_checkout_url(self, product_id: str) -> str:
        """Get direct checkout URL for a product."""
        if not self.running:
            return ""
        return f"http://{self.host}:{self.port}/checkout?id={product_id}"
    
    def get_checkout_url_by_url(self, product_url: str) -> str:
        """Get direct checkout URL for a product URL."""
        if not self.running:
            return ""
        from urllib.parse import quote
        return f"http://{self.host}:{self.port}/checkout-url?url={quote(product_url)}"


# Global server instance
_server_instance: Optional[FastCheckoutServer] = None

def get_server() -> FastCheckoutServer:
    """Get or create the global server instance."""
    global _server_instance
    if _server_instance is None:
        _server_instance = FastCheckoutServer()
    return _server_instance

def start_server() -> str:
    """Start the fast checkout server."""
    return get_server().start()

def stop_server():
    """Stop the fast checkout server."""
    server = get_server()
    server.stop()

def get_checkout_url(product_id: str) -> str:
    """Get direct checkout URL for a product."""
    return get_server().get_checkout_url(product_id)

def get_checkout_url_by_url(product_url: str) -> str:
    """Get direct checkout URL for a product URL."""
    return get_server().get_checkout_url_by_url(product_url)


if __name__ == "__main__":
    # Standalone server mode
    import sys
    logging.basicConfig(level=logging.INFO)
    
    server = FastCheckoutServer()
    base_url = server.start()
    
    if base_url:
        print(f"🚀 Fast checkout server running at {base_url}")
        print("   Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 Stopping server...")
            server.stop()
    else:
        print("❌ Failed to start server")
        sys.exit(1)
