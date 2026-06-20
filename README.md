# Street Cleaning solver

Run the constructive baseline:

```bash
python3 main.py data/input/train_a.txt data/output/train_a.txt --restarts 32
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

Validate a generated submission independently:

```bash
python3 validate.py data/input/train_a.txt data/output/train_a.txt
```

The parser accepts both the documented input form (with `N` coordinate lines)
and the supplied datasets (which omit those lines).

The submission route count follows the provided examples and judge: it is the
number of traversed streets, so the following route line contains `count + 1`
junctions. This differs from the prose in the problem statement.
