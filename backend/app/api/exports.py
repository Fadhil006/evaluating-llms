"""Download allowlisted experiment reports (mount independently)."""

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.services.exports import render_csv, render_html, render_json, render_markdown, report_data

router = APIRouter(prefix="/api/experiments", tags=["exports"])


@router.get("/{experiment_id}/export")
def export_experiment(request: Request, experiment_id: int,
                      format: str = Query("json", pattern="^(csv|json|html|markdown)$")):
    with request.app.state.sessions.begin() as session:
        data = report_data(session, experiment_id, getattr(request.app.state, "export_redactions", []))
    if data is None:
        raise HTTPException(404, "Experiment not found")
    renderer, media = {"json": (render_json, "application/json"),
                       "csv": (render_csv, "text/csv; charset=utf-8"),
                       "html": (render_html, "text/html; charset=utf-8"),
                       "markdown": (render_markdown, "text/markdown; charset=utf-8")}[format]
    return Response(renderer(data), media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="experiment-{experiment_id}.{format}"'})
