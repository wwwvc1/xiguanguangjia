"""
报告 API
- GET /api/reports?type=weekly|monthly  列表
- GET /api/reports/{id}                详情
- POST /api/reports/generate           手动生成
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from utils.deps import get_current_user
from utils.report_generator import list_reports, get_report, generate_weekly_report, generate_monthly_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/")
def get_reports(
    current_user: int = Depends(get_current_user),
    type: str = Query(None, pattern="^(weekly|monthly)$")
):
    return list_reports(current_user, type)


@router.get("/{report_id}")
def get_report_detail(report_id: int, current_user: int = Depends(get_current_user)):
    r = get_report(current_user, report_id)
    if not r:
        raise HTTPException(status_code=404, detail="报告不存在")
    return r


@router.post("/generate")
def generate_report(
    current_user: int = Depends(get_current_user),
    type: str = Query(..., pattern="^(weekly|monthly)$"),
    period: str = Query(None, description="周报 '2026-W34' / 月报 '2026-08',不传则当期"),
    force: bool = Query(False, description="true 时直接覆盖同周期报告;否则同周期已存在返回 409")
):
    # 算 period
    from datetime import datetime
    if not period:
        if type == "weekly":
            iso = datetime.now().isocalendar()
            period = f"{iso[0]}-W{iso[1]:02d}"
        else:
            period = datetime.now().strftime("%Y-%m")

    # 同周期已存在时:除非 force=true,否则拒绝
    if not force:
        from utils.report_generator import list_reports
        existing = [r for r in list_reports(current_user, type) if r.get("period") == period]
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"该周期报告已存在(id={existing[0]['id']}),如需重新生成请传 force=true"
            )

    if type == "weekly":
        return generate_weekly_report(current_user, period)
    return generate_monthly_report(current_user, period)
