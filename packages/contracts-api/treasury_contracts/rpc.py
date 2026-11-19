"""Batch independent read-only contract calls at an explicit block number."""


def read_functions(w3, functions, block):
    if type(block) is not int or block < 0:
        raise ValueError("batch reads require an explicit block")
    functions = list(functions)
    with w3.batch_requests() as batch:
        for fn in functions:
            batch.add(fn.call(block_identifier=block))
        result = batch.execute()
    if len(result) != len(functions):
        raise ValueError("incomplete RPC batch")
    return result
