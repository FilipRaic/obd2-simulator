# models3d.py - the list of 3D models that have to be attached to footprints by
# hand.
#
# Factored out of build_board.py so two scripts can share the same list:
# build_board.py, which builds the board from scratch, and apply_3dmodels.py,
# which attaches models to an ALREADY ROUTED board without re-routing it.
#
# The render was missing parts for two reasons: U1 and U9 pointed at models that
# do not exist under that name in KiCad's library, and J2, ENC1 and SW6 have no
# model at all (J2 and SW6 are custom footprints, and the stock encoder footprint
# RotaryEncoder_Alps_EC11E ships without a model in KiCad 10). For U1 and U9
# existing models of the same package were used, and for the rest there are
# custom VRML models in kicad/3dmodels/, printed by scripts/gen_3dmodels.py.

MODEL_FIX = {
    # ESSOP-10 is an SSOP-10 with a thermal pad, same body outline
    "U1":   "${KICAD10_3DMODEL_DIR}/Package_SO.3dshapes/SSOP-10-1EP_3.9x4.9mm_P1mm_EP2.1x3.3mm.step",
    # TI's own VSON-10 model (DRC0010J)
    "U9":   "${KICAD10_3DMODEL_DIR}/Package_SON.3dshapes/Texas_S-PVSON-N10.step",
    "J2":   "${KIPRJMOD}/3dmodels/SEP-A-OBD-D2.wrl",
    "SW6":  "${KIPRJMOD}/3dmodels/SKRHABE010.wrl",
    "ENC1": "${KIPRJMOD}/3dmodels/EN11-HSB1AQ20.wrl",
}


def apply_models(board, pcbnew):
    """Attach the MODEL_FIX models to the footprints on the board. Returns the
    list of reference designators that were touched."""
    done = []
    for fp in board.GetFootprints():
        path = MODEL_FIX.get(fp.GetReference())
        if not path:
            continue
        fp.Models().clear()
        m = pcbnew.FP_3DMODEL()
        m.m_Filename = path
        m.m_Show = True
        m.m_Opacity = 1.0
        fp.Models().push_back(m)
        done.append(fp.GetReference())
    return sorted(done)
