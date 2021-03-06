# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

import logging

from flask import jsonify
from flask import request

from bkr.server import identity
from bkr.server.app import app
from bkr.server.flask_util import auth_required, read_json_request, Unauthorised401, UnsupportedMediaType415
from bkr.server.model import User

log = logging.getLogger(__name__)


@app.route("/auth/login", methods=["POST"])
def login_password():
    """
    Authenticates the current session using the given username and password.

    The caller may act as a proxy on behalf of another user by passing the
    *proxy_user* key. This requires that the caller has 'proxy_auth'
    permission.
    The request must contain Authorization header that contains the word Basic
    followed by a space and a base64-encoded string username:password.
    Proxy_user is optional.

    :jsonparam string proxy_user: Username on whose behalf the caller is proxying

    """

    try:
        payload = read_json_request(request)
        proxy_user = payload.get("proxy_user")
    except UnsupportedMediaType415:
        proxy_user = None

    if not request.authorization:
        raise Unauthorised401("Authorization header is missing")
    username = request.authorization.username
    password = request.authorization.password

    user = User.by_user_name(username)
    if (user is None
            or not user.can_log_in()
            or not user.check_password(password)):
        raise Unauthorised401(u"Invalid username or password")

    if proxy_user:
        if not user.has_permission("proxy_auth"):
            raise Unauthorised401("%s does not have proxy_auth permission" % user.user_name)
        proxied_user = User.by_user_name(proxy_user)
        if proxied_user is None:
            raise Unauthorised401("Proxy user %s does not exist" % proxy_user)
        identity.set_authentication(proxied_user, proxied_by=user)
    else:
        identity.set_authentication(user)
    return jsonify({"username": user.user_name})


@app.route("/auth/logout", methods=["POST"])
def logout():
    """
    Invalidates the current session.
    """
    identity.clear_authentication()
    return jsonify({"message": True})


@app.route("/auth/whoami", methods=["GET"])
@auth_required
def who_am_i():
    """
    Returns an JSON with information about the
    currently logged in user.
    Provided for testing purposes.

    """
    retval = {"username": identity.current.user.user_name,
              "email_address": identity.current.user.email_address}
    if identity.current.proxied_by_user is not None:
        retval["proxied_by_username"] = identity.current.proxied_by_user.user_name
    return jsonify(retval)
