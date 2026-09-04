from app.domain.runs import Op


class OperationRoutingError(ValueError):
    pass


def resolve_op(*, has_base: bool, has_mask: bool, connect_count: int) -> Op:
    if connect_count < 0 or connect_count > 2:
        raise OperationRoutingError("A run accepts between zero and two connects")
    if has_mask and not has_base:
        raise OperationRoutingError("A mask requires a resolved base version")

    match has_base, has_mask, connect_count > 0:
        case False, False, False:
            return Op.GENERATE
        case False, False, True:
            return Op.GENERATE_REF
        case True, False, False:
            return Op.EDIT_INSTRUCT
        case True, True, False:
            return Op.EDIT_INPAINT
        case True, True, True:
            return Op.EDIT_COMPOSITE
        case True, False, True:
            return Op.EDIT_REF_GUIDED

    raise OperationRoutingError("Unsupported run input combination")
