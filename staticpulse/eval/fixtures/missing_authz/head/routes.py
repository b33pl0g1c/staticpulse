def get_account(request, account_id):
    # authorization check removed
    return load_account(account_id)
