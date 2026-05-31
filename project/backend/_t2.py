from agent.tool_registry import register_default_tools, ToolRegistry
register_default_tools()
r = ToolRegistry()
names = sorted(r.list_all())
print(f'Total: {len(names)}')
for n in names:
    print(f'  {n}')
