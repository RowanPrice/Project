# The original prototype

These are the files this project started as, kept because they are the record
of how it began and because the artwork is still good.

`controller.py`, `nuclear.py`, `battery.py` and `science.py` were the first
model: reactor temperature was a linear function of average rod depth plus a
couple of degrees of noise, the battery charged and discharged at a fixed rate,
and the upgrade catalogue described its effects in strings that nothing read.
`interface.py` was a Pygame front end, later replaced by the Flask one.

Everything here has been superseded by the `reactorsim` package, which models
the same plant with real point kinetics, xenon poisoning, thermal hydraulics
and a protection system. Nothing in the running game imports anything in this
folder; it is not on the import path and it is not tested.

The SVGs are unused for now. They deserve a better home than this.
