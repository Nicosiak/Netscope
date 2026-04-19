# NetScope — quick commands (no need to type paths each time)
.PHONY: run stop

run:
	@bash scripts/run_app.sh

stop:
	@pids=$$(lsof -ti tcp:8765 2>/dev/null); if [ -n "$$pids" ]; then kill -9 $$pids && echo "Stopped process on port 8765."; else echo "Nothing listening on 8765."; fi
