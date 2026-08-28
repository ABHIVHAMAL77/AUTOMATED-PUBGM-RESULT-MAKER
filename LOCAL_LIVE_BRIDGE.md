# Local Live Feed Bridge

Use this only if the hosted website cannot read `http://127.0.0.1:10086/gettotalplayerlist` directly from Chrome.

## Steps on the game PC

1. Keep the PUBG Mobile observer feed running.
2. Double-click `run_live_bridge.bat`.
3. Open the website Live API page.
4. Choose `This browser`.
5. Change the URL to:

```text
http://127.0.0.1:8765/gettotalplayerlist
```

6. Press `Start 1s live`.

The bridge reads the real observer feed from the same PC and gives Chrome the browser permission headers needed by the hosted website.
