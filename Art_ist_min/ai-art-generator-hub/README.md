# Agentic Art Frontend

React frontend for the local Agentic Art prototype. This app is intended to run with the FastAPI backend in the repository root.

## Stack

- Vite
- TypeScript
- React
- shadcn/ui
- Tailwind CSS
- TanStack Query

## Development

```sh
npm install
npm run dev
```

The frontend expects the backend API at `/api` by default. Override with `VITE_API_BASE` if needed.

## Current scope

- Collect prompt text, image references, video references, and advanced generation fields
- Preview the generated request payload before backend submission
- View placeholder agent status through the status route

## Current limitation

Generation remains backend-disabled until the ComfyUI workflow bridge is restored.
