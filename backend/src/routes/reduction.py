import json
from fastapi import APIRouter,Depends,Response
from ..config.database import get_db
from ..schemas.reduction import ReductionInput,ReductionExtend
from ..services.auth import current_user,writer
from ..services.reduction import listing,create,detail,extend,replay
router=APIRouter(prefix='/reductions')
@router.get('')
def get(db=Depends(get_db),user=Depends(current_user)):return listing(db)
@router.post('',status_code=202)
def add(data:ReductionInput,db=Depends(get_db),user=Depends(writer)):return create(db,data)
@router.get('/{ident}')
def one(ident:int,db=Depends(get_db),user=Depends(current_user)):return detail(db,ident)
@router.post('/{ident}/extend',status_code=202)
def more(ident:int,data:ReductionExtend,db=Depends(get_db),user=Depends(writer)):return extend(db,ident,data.amount)
@router.post('/{ident}/replay')
def replay_sample(ident:int,db=Depends(get_db),user=Depends(current_user)):return replay(db,ident)
@router.get('/{ident}/export')
def export(ident:int,db=Depends(get_db),user=Depends(current_user)):
    return Response(json.dumps(detail(db,ident),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="lsm-reduction-{ident}.json"'})
