from ibm_watsonx_ai.metanames import GenTextParamsMetaNames
from langchain_ibm import ChatWatsonx
from typing import Any
from contextlib import asynccontextmanager, AsyncExitStack
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv
import os, json, asyncio, logging, shutil
load_dotenv()

def format_for_llm(name, description, input_schema):
    args_desc = []
    if "properties" in input_schema:
        for param_name, param_info in input_schema["properties"].items():
            arg_desc = (
                f"- {param_name}: {param_info.get('description', 'No description')}"
            )
            if param_name in input_schema.get("required", []):
                arg_desc += " (required)"
            args_desc.append(arg_desc)
    return f"""
Tool: {name}
Description: {description}
Arguments:
{args_desc}
"""

llm = ChatWatsonx(
    model_id=os.environ['MODEL_ID'],
    url=os.environ['WATSONX_URL'],
    project_id=os.environ['WATSONX_PROJECT_ID'],
    params={
        GenTextParamsMetaNames.MAX_NEW_TOKENS: 2500,
        GenTextParamsMetaNames.MIN_NEW_TOKENS: 20,
        GenTextParamsMetaNames.DECODING_METHOD: 'greedy',
        
    },
)

class Configuration:
    def __init__(self) -> None:
        self.load_env()
        self.api_key = os.getenv("WATSONX_APIKEY")

    @staticmethod
    def load_env() -> None:
        load_dotenv()

    @staticmethod
    def load_config(file_path: str) -> dict[str, Any]:
        with open(file_path, "r") as f:
            return json.load(f)

    @property
    def llm_api_key(self) -> str:
        if not self.api_key:
            raise ValueError("LLM_API_KEY not found in environment variables")
        return self.api_key



class Server:
    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name: str = name
        self.config: dict[str, Any] = config
        self.stdio_context: Any | None = None
        self.session: ClientSession | None = None
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.exit_stack: AsyncExitStack = AsyncExitStack()
    
    async def initialize(self) -> None:
        command = (
            shutil.which("npx")
            if self.config["command"] == "npx"
            else self.config["command"]
        )
        if command is None:
            raise ValueError("The command must be a valid string and cannot be None.")

        server_params = StdioServerParameters(
            command=command,
            args=self.config["args"],
            env={name: os.environ[name] for name in self.config["env"]}
            if self.config.get("env")
            else None,
        )
        try:
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = stdio_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self.session = session
        except Exception as e:
            logging.error(f"Error initializing server {self.name}: {e}")
            await self.cleanup()
            raise
        
    async def list_tools(self) -> list[Any]:
        if not self.session:
            raise RuntimeError(f"Server {self.name} not initialized")

        tools_response = await load_mcp_tools(self.session)
        tools = []
        for tool in tools_response:
            tools.append(
                format_for_llm(tool.name, tool.description, tool.args_schema)
            )
        return tools, tools_response
    
    async def cleanup(self) -> None:
        """Clean up server resources."""
        async with self._cleanup_lock:
            try:
                await self.exit_stack.aclose()
                self.session = None
                self.stdio_context = None
            except Exception as e:
                logging.error(f"Error during cleanup of server {self.name}: {e}")


      
@asynccontextmanager
async def main(query):
    config = Configuration()
    server_config = config.load_config("servers_config.json")
    servers = [
        Server(name, srv_config)
        for name, srv_config in server_config["mcpServers"].items()
    ]
    all_tools = []
    for server in servers:
        await server.initialize()
        tools,tools_response = await server.list_tools()
        all_tools.extend(tools)
    print("all tools: ", all_tools)
    message = (
                "You are a helpful assistant with access to these tools:\n\n"
                f"{all_tools}\n"
                "Choose the appropriate tool based on the user's question. "
                "If no tool is needed, reply directly.\n\n"
                "IMPORTANT: When you need to use a tool, you must ONLY respond with "
                "the exact JSON object format below, nothing else:\n"
                "{\n"
                '    "tool": "tool-name",\n'
                '    "arguments": {\n'
                '        "argument-name": "value"\n'
                "    }\n"
                "}\n\n"
                "After receiving a tool's response:\n"
                "1. Transform the raw data into a natural, conversational response\n"
                "2. Keep responses concise but informative\n"
                "3. Focus on the most relevant information\n"
                "4. Use appropriate context from the user's question\n"
                "5. Avoid simply repeating the raw data\n\n"
                "Please use only the tools that are explicitly defined above."
                f"User query: ${query}"
            )
    agent = create_react_agent(
                llm,
                tools=tools_response,
                prompt= message
            )
            
    yield agent
    for server in servers:
        await server.cleanup() 
    
async def invoke_agent(query):
    async with main(query) as agent:
        agent_response = await agent.ainvoke({"messages": query})
        return agent_response['messages'][-1].content

