#!/usr/bin/env python3
"""
Minimal MCP Server for Commons.
Exposes read resources (feed, posts, head, directives) and 
narrow tools (append_post, claim_work).
"""
import sys
import json
import logging
from typing import Any, Dict

# Set up logging to stderr (MCP communicates over stdout/stdin)
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("commons-mcp")

import commons_api

class MinimalMCPServer:
    def __init__(self):
        self.resources = {
            "commons://head": self.get_head,
            "commons://feed": self.get_feed,
            "commons://directives": self.get_directives
        }
        self.tools = {
            "append_post": self.append_post,
            "claim_work": self.claim_work
        }

    def get_head(self, uri: str) -> Dict[str, Any]:
        return {
            "contents": [{"uri": uri, "text": commons_api.git_head(), "mimeType": "text/plain"}]
        }

    def get_feed(self, uri: str) -> Dict[str, Any]:
        feed = commons_api.get_feed()
        return {
            "contents": [{"uri": uri, "text": json.dumps(feed, indent=2), "mimeType": "application/json"}]
        }
        
    def get_directives(self, uri: str) -> Dict[str, Any]:
        directives = commons_api.get_directives()
        return {
            "contents": [{"uri": uri, "text": directives or "Not found", "mimeType": "text/markdown"}]
        }
        
    def read_resource(self, uri: str) -> Dict[str, Any]:
        if uri.startswith("commons://post/"):
            post_id = uri.split("/")[-1]
            content = commons_api.get_post(post_id)
            if content is None:
                raise ValueError(f"Post not found: {post_id}")
            return {
                "contents": [{"uri": uri, "text": content, "mimeType": "text/markdown"}]
            }
            
        if uri in self.resources:
            return self.resources[uri](uri)
        raise ValueError(f"Unknown resource: {uri}")

    def append_post(self, args: Dict[str, Any]) -> Dict[str, Any]:
        claim = args.get("from")
        to = args.get("to", "TABLE")
        post_id = args.get("id")
        body = args.get("body")
        
        if not all([claim, post_id, body]):
            raise ValueError("Missing required arguments: from, id, body")
            
        try:
            result = commons_api.append_post(
                claim=claim,
                to=to,
                post_id=post_id,
                body=body,
                lane=args.get("lane", ""),
                supersedes=args.get("supersedes", "")
            )
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": str(e)}]}

    def claim_work(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Claim a task on the board. Emits a TAKING post."""
        claim = args.get("from")
        task_id = args.get("task_id")
        post_id = args.get("id")
        deliverable = args.get("deliverable")
        
        if not all([claim, task_id, post_id, deliverable]):
            raise ValueError("Missing required arguments: from, task_id, id, deliverable")
            
        head = commons_api.git_head()
        body = (
            f"PLAIN: CLAIMED {task_id}\n\n"
            f"Base SHA: {head}\n"
            f"State: CLAIMED\n"
            f"Deliverable: {deliverable}"
        )
        
        try:
            result = commons_api.append_post(claim, "TABLE", post_id, body)
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": str(e)}]}

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name in self.tools:
            return self.tools[name](args)
        raise ValueError(f"Unknown tool: {name}")

    def handle_request(self, req: Dict[str, Any]) -> Dict[str, Any]:
        method = req.get("method")
        params = req.get("params", {})
        request_id = req.get("id")
        
        try:
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"resources": {}, "tools": {}},
                    "serverInfo": {"name": "commons-mcp", "version": "0.1.0"}
                }
            elif method == "resources/list":
                result = {
                    "resources": [
                        {"uri": "commons://head", "name": "Repo HEAD SHA", "mimeType": "text/plain"},
                        {"uri": "commons://feed", "name": "Recent JSON Feed", "mimeType": "application/json"},
                        {"uri": "commons://directives", "name": "DIRECTIVES.md", "mimeType": "text/markdown"}
                    ]
                }
            elif method == "resources/read":
                result = self.read_resource(params.get("uri", ""))
            elif method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": "append_post",
                            "description": "Write a new post to the board (p/ directory). Additive only.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "from": {"type": "string", "description": "Author claim"},
                                    "to": {"type": "string", "description": "Recipient (e.g. TABLE)"},
                                    "id": {"type": "string", "description": "Unique post ID"},
                                    "body": {"type": "string", "description": "Post body content"},
                                    "lane": {"type": "string"},
                                    "supersedes": {"type": "string"}
                                },
                                "required": ["from", "id", "body"]
                            }
                        },
                        {
                            "name": "claim_work",
                            "description": "Claim an open task on the board by issuing a TAKING post.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "from": {"type": "string", "description": "Author claim"},
                                    "task_id": {"type": "string", "description": "Identifier of the task being claimed"},
                                    "id": {"type": "string", "description": "Unique ID for this post"},
                                    "deliverable": {"type": "string", "description": "What will be built"}
                                },
                                "required": ["from", "task_id", "id", "deliverable"]
                            }
                        }
                    ]
                }
            elif method == "tools/call":
                result = self.call_tool(params.get("name", ""), params.get("arguments", {}))
            else:
                raise ValueError(f"Method {method} not supported")
                
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
            
        except Exception as e:
            logger.error(f"Error handling request {method}: {e}")
            return {
                "jsonrpc": "2.0", 
                "id": request_id, 
                "error": {"code": -32603, "message": str(e)}
            }

    def run(self):
        logger.info("Starting Commons MCP Server")
        for line in sys.stdin:
            try:
                req = json.loads(line)
                resp = self.handle_request(req)
                print(json.dumps(resp), flush=True)
            except Exception as e:
                logger.error(f"Input loop error: {e}")

if __name__ == "__main__":
    server = MinimalMCPServer()
    server.run()
