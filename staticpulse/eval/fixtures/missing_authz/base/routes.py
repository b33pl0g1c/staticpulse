def get_account(request, account_id):
    if request.user.id != account_id:
        raise PermissionError("forbidden")
    return load_account(account_id)
