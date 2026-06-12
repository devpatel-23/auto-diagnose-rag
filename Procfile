# Procfile
# ---------
# Used by Render, Heroku, and other PaaS platforms to know how to start services.
# Each line: <process_type>: <command>
#
# Render will run the `web` process automatically.
# It injects the $PORT environment variable.

web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
