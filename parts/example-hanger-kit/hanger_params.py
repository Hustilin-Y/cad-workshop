"""example-hanger-kit: the parameters the mount and both arm folders share.

A made-up 400 mm object (a slim LED bar, say) hung 200 mm below the ceiling: its -X end is a
32 x 16 mm block, its +X end a flat 32 x 7.2 mm plate. Every piece's model.py loads this file.
"""

from cadlib.style.archetypes.hanger import EndProfile, HangerSpec

STYLE = "gothic"        # gothic, gaudi, hitech, parametric or biomech
SPEC = HangerSpec(
    span=400,                           # between the object's end faces, mm
    end_a=EndProfile("rect", 32, 16),   # -X end: width (Y) x height (Z), mm
    end_b=EndProfile("rect", 32, 7.2),  # +X end, mm
    drop=200,                           # ceiling to the object's bottom, mm
)
