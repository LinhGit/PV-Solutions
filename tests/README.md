### Run Tests

Run test suite within Docker container in `/pvextractor` directory with the command
```
python -m unittest tests/test_*.py
```

### Coverage Report

Make sure coverage is installed by running
```
python -m pip install coverage
```

Analyze coverage by running the following command from project root
```
coverage run --source=. --branch -m unittest tests/test_*.py
```

View coverage report with
```
coverage report -m
```
or the html version with
```
coverage html
```

### Mutation Testing

Install mutmut
```
python -m pip install mutmut
```

Perform mutation tests of a single test case with
```
mutmut --paths-to-mutate="tests/test_quadrilaterals.py" --runner="python -m unittest" run
```
where `test_quadrilaterals` could be any other test case module.
Or run it for all modules with
```
mutmut --paths-to-mutate="tests/test_*.py" --runner="python -m unittest" run
```

### Origin of Test Data

Important: Do not create new test data, otherwise you may generate test data with updated (possibly buggy) code! Instead, keep the origin test data and make sure updated code passes all tests. The only reason for updating the test data is an update of the dataset structure. Note, however that this also requires updating downstream tools, such as PV Drone Inspect Viewer.

Test data in `tests/data` was created by running the pipeline within Docker container in `/pvextractor` directory with the command
```
python main.py tests/config.yml
```
After completion, the updated test data is available in `tests/data`.
