
from turbogears import identity, redirect, config, controllers, expose, \
        flash, widgets, validate, error_handler, validators, redirect, \
        paginate, url
from turbogears.database import session
from turbogears.widgets import AutoCompleteField
from sqlalchemy.orm.exc import NoResultFound
from cherrypy import request, response
from tg_expanding_form_widget.tg_expanding_form_widget import ExpandingForm
from kid import Element
from bkr.server.validators import StrongPassword
from bkr.server.xmlrpccontroller import RPCRoot
from bkr.server.helpers import *
from bkr.server.widgets import BeakerDataGrid, myPaginateDataGrid, \
    GroupPermissions, DeleteLinkWidgetForm
from bkr.server.admin_page import AdminPage
from bkr.server.bexceptions import BX 
from bkr.server.controller_utilities import restrict_http_method
import cherrypy
from bkr.server import mail

# from bkr.server import json
# import logging
# log = logging.getLogger("bkr.server.controllers")
#import model
from model import *
import string

def make_edit_link(name, id):
    # make an edit link
    return make_link(url  = 'edit?group_id=%s' % id,
                     text = name)


class GroupFormSchema(validators.Schema):
    display_name = validators.UnicodeString(not_empty=True, max=256, strip=True)
    group_name = validators.UnicodeString(not_empty=True, max=256, strip=True)
    root_password = StrongPassword()
    ldap = validators.StringBool(if_empty=False)

class GroupForm(widgets.TableForm):
    name = 'Group'
    fields = [
        widgets.HiddenField(name='group_id'),
        widgets.TextField(name='group_name', label=_(u'Group Name')),
        widgets.TextField(name='display_name', label=_(u'Display Name')),
        widgets.PasswordField(name='root_password', label=_(u'Root Password'),
            validator=StrongPassword()),
        widgets.CheckBox(name='ldap', label=_(u'LDAP'),
                help_text=_(u'Populate group membership from LDAP?')),
    ]
    action = 'save_data'
    submit_text = _(u'Save')
    validator = GroupFormSchema()

    def update_params(self, d):
        if not identity.current.user.is_admin() or \
                not config.get('identity.ldap.enabled', False):
            d['disabled_fields'] = ['ldap']
        super(GroupForm, self).update_params(d)

class Groups(AdminPage):
    # For XMLRPC methods in this class.
    exposed = True
    group_id     = widgets.HiddenField(name='group_id')
    auto_users    = AutoCompleteField(name='user',
                                     search_controller = url("/users/by_name"),
                                     search_param = "input",
                                     result_name = "matches")
    auto_systems  = AutoCompleteField(name='system',
                                     search_controller = url("/by_fqdn"),
                                     search_param = "input",
                                     result_name = "matches")

    search_groups = AutoCompleteField(name='group',
                                     search_controller = url("/groups/by_name?anywhere=1"),
                                     search_param = "name",
                                     result_name = "groups")

    search_permissions = AutoCompleteField(name='permissions',
                                     search_controller = url("/groups/get_permissions"),
                                     search_param = "input",
                                     result_name = "matches")

    group_form = GroupForm()

    permissions_form = widgets.RemoteForm(
        'Permissions',
        fields = [search_permissions, group_id],
        submit_text = _(u'Add'),
        on_success = 'add_group_permission_success(http_request.responseText)',
        on_failure = 'add_group_permission_failure(http_request.responseText)',
        before = 'before_group_permission_submit()',
        after = 'after_group_permission_submit()',
    )

    group_user_form = widgets.TableForm(
        'GroupUser',
        fields = [group_id, auto_users],
        action = 'save_data',
        submit_text = _(u'Add'),
    )

    group_system_form = widgets.TableForm(
        'GroupSystem',
        fields = [group_id, auto_systems],
        action = 'save_data',
        submit_text = _(u'Add'),
    )

    delete_link = DeleteLinkWidgetForm()

    def __init__(self,*args,**kw):
        kw['search_url'] =  url("/groups/by_name?anywhere=1")
        kw['search_name'] = 'group'
        kw['widget_action'] = './admin'
        super(Groups,self).__init__(*args,**kw)

        self.search_col = Group.group_name
        self.search_mapper = Group

    @expose(format='json')
    def by_name(self, input,*args,**kw):
        input = input.lower()
        if 'anywhere' in kw:
            search = Group.list_by_name(input, find_anywhere=True)
        else:
            search = Group.list_by_name(input)

        groups =  [match.group_name for match in search]
        return dict(matches=groups)

    @expose(format='json')
    @identity.require(identity.not_anonymous())
    def remove_group_permission(self, group_id, permission_id):
        try:
            group = Group.by_id(group_id)
        except NoResultFound:
            log.exception('Group id %s is not a valid Group to remove' % group_id)
            return ['0']

        if not group.can_edit(identity.current.user):
            log.exception('User %d does not have edit permissions for Group id %s'
                          % (identity.current.user.user_id, group_id))
            response.status = 403
            return ['You are not an owner of group %s' % group]

        try:
            permission = Permission.by_id(permission_id)
        except NoResultFound:
            log.exception('Permission id %s is not a valid Permission to remove' % permission_id)
            return ['0']
        group.permissions.remove(permission)
        return ['1']

    @expose(format='json')
    def get_permissions(self, input):
        results = Permission.by_name(input, anywhere=True)
        permission_names = [result.permission_name for result in results]
        return dict(matches=permission_names)

    @identity.require(identity.not_anonymous())
    @expose(template='bkr.server.templates.form')
    def new(self, **kw):
        return dict(
            form = self.group_form,
            title = 'New Group',
            action = './save_new',
            options = {},
            value = kw,
        )

    def show_members(self, group):
        user_fields = [
            ('User Members', lambda x: x.display_name),
        ]
        can_edit = False
        if identity.current.user:
            can_edit = group.can_modify_membership(identity.current.user)
        if can_edit:
            user_fields.append((' ', lambda x: make_link(
                    'removeUser?group_id=%s&id=%s' % (group.group_id, x.user_id),
                    u'Remove (-)')))
        return widgets.DataGrid(fields=user_fields)

    @expose(template='bkr.server.templates.grid')
    @paginate('list', default_order='fqdn', limit=20, max_limit=None)
    def systems(self,group_id=None,*args,**kw):
        try:
            group = Group.by_id(group_id)
        except NoResultFound:
            log.exception('Group id %s is not a valid group id' % group_id)
            flash(_(u'Need a valid group to search on'))
            redirect('../groups/mine')

        systems = System.all(identity.current.user).filter(System.groups.contains(group))
        title = 'Systems in Group %s' % group.group_name
        from bkr.server.controllers import Root
        return Root()._systems(systems,title, group_id = group_id,**kw)

    @expose(template='bkr.server.templates.group_users')
    def group_members(self, group_id, **kw):
        try:
            group = Group.by_id(group_id)
        except NoResultFound:
            log.exception('Group id %s is not a valid group id' % group_id)
            flash(_(u'Need a valid group to search on'))
            redirect('../groups/')
        usergrid = self.show_members(group)
        return dict(value = group,grid = usergrid)

    @identity.require(identity.not_anonymous())
    @expose(template='bkr.server.templates.group_form')
    def edit(self, group_id, **kw):
        try:
            group = Group.by_id(group_id)
        except NoResultFound:
            log.exception('Group id %s is not a valid group id' % group_id)
            flash(_(u'Need a valid group to search on'))
            redirect('../groups/mine')
        if not group.can_edit(identity.current.user):
            flash(_(u'You are not an owner of group %s' % group))
            redirect('../groups/mine')
        usergrid = self.show_members(group)
        systemgrid = widgets.DataGrid(fields=[
                                  ('System Members', lambda x: x.fqdn),
                                  (' ', lambda x: make_link('removeSystem?group_id=%s&id=%s' % (group_id, x.id), u'Remove (-)')),
                              ])
        group_permissions_grid = self.show_permissions()
        group_permissions = GroupPermissions()
        return dict(
            form = self.group_form,
            system_form = self.group_system_form,
            user_form = self.group_user_form,
            action = './save',
            system_action = './save_system',
            user_action = './save_user',
            options = {},
            value = group,
            usergrid = usergrid,
            systemgrid = systemgrid,
            disabled_fields = ['System Members'],
            group_permissions = group_permissions,
            group_form = self.permissions_form,
            group_permissions_grid = group_permissions_grid,
        )

    def _new_group(self, group_id, display_name, group_name, ldap,
        root_password):
        user = identity.current.user
        if ldap and not user.is_admin():
            flash(_(u'Only admins can create LDAP groups'))
            redirect('.')
        try:
            Group.by_name(group_name)
        except NoResultFound:
            pass
        else:
            flash( _(u"Group %s already exists." % group_name) )
            redirect(".")
        group = Group()
        session.add(group)
        activity = Activity(user, u'WEBUI', u'Added', u'Group', u"", display_name)
        group.display_name = display_name
        group.group_name = group_name
        group.ldap = ldap
        if group.ldap:
            group.refresh_ldap_members()
        group.root_password = root_password
        if not ldap: # LDAP groups don't have owners
            group.user_group_assocs.append(UserGroup(user=user, is_owner=True))
            group.activity.append(GroupActivity(user, service=u'WEBUI',
                action=u'Added', field_name=u'User',
                old_value=None, new_value=user.user_name))
            group.activity.append(GroupActivity(user, service=u'WEBUI',
                action=u'Added', field_name=u'Owner',
                old_value=None, new_value=user.user_name))
        return group

    @identity.require(identity.not_anonymous())
    @expose()
    @validate(form=group_form)
    @error_handler(new)
    def save_new(self, group_id=None, display_name=None, group_name=None,
        ldap=False, root_password=None, **kwargs):
        # save_new() is needed because 'edit' is not a viable
        # error handler for new groups.
        self._new_group(group_id, display_name, group_name, ldap,
            root_password)
        flash( _(u"OK") )
        redirect("mine")

    @identity.require(identity.not_anonymous())
    @expose()
    @validate(form=group_form)
    @error_handler(edit)
    def save(self, group_id=None, display_name=None, group_name=None,
        ldap=False, root_password=None, **kwargs):

        user = identity.current.user

        if ldap and not user.is_admin():
            flash(_(u'Only admins can create LDAP groups'))
            redirect('mine')

        try:
            group = Group.by_id(group_id)
        except NoResultFound:
            flash( _(u"Group %s does not exist." % group_id) )
            redirect('mine')

        if not group.can_edit(user):
            flash(_(u'You are not an owner of group %s' % group))
            redirect('../groups/mine')

        try:
            group.set_name(user, u'WEBUI', group_name)
            group.set_display_name(user, u'WEBUI', display_name)
            group.ldap = ldap
            group.root_password = root_password
        except BeakerException, err:
            session.rollback()
            flash(_(u'Failed to update group %s: %s' %
                                                    (group.group_name, err)))
            redirect('.')

        flash( _(u"OK") )
        redirect("mine")

    @identity.require(identity.not_anonymous())
    @expose()
    @error_handler(edit)
    def save_system(self, **kw):
        system = System.by_fqdn(kw['system']['text'],identity.current.user)
        group = Group.by_id(kw['group_id'])
        if group in system.groups:
            flash( _(u"System '%s' is already in group '%s'" % (system.fqdn, group.group_name)))
            redirect("./edit?group_id=%s" % kw['group_id'])
        group.systems.append(system)

        if not group.can_edit(identity.current.user):
            flash(_(u'You are not an owner of group %s' % group))
            redirect('../groups/mine')

        activity = GroupActivity(identity.current.user, u'WEBUI', u'Added', u'System', u"", system.fqdn)
        sactivity = SystemActivity(identity.current.user, u'WEBUI', u'Added', u'Group', u"", group.display_name)
        group.activity.append(activity)
        system.activity.append(sactivity)
        flash( _(u"OK") )
        redirect("./edit?group_id=%s" % kw.get('group_id'))

    @identity.require(identity.in_group("admin"))
    @expose(format='json')
    def save_group_permissions(self, **kw):
        try:
            permission_name = kw['permissions']['text']
        except KeyError, e:
            log.exception('Permission not submitted correctly')
            response.status = 403
            return ['Permission not submitted correctly']
        try:
            permission = Permission.by_name(permission_name)
        except NoResultFound:
            log.exception('Invalid permission: %s' % permission_name)
            response.status = 403
            return ['Invalid permission value']
        try:
            group_id = kw['group_id']
        except KeyError:
            log.exception('Group id not submitted')
            response.status = 403
            return ['No group id given']
        try:
            group = Group.by_id(group_id)
        except NoResultFound:
            log.exception('Group id %s is not a valid group id' % group_id)
            response.status = 403
            return ['Invalid Group Id']

        group = Group.by_id(group_id)
        if permission not in group.permissions:
            group.permissions.append(permission)
        else:
            response.status = 403
            return ['%s already exists in group %s' %
                (permission.permission_name, group.group_name)]

        return {'name':permission_name, 'id':permission.permission_id}

    @identity.require(identity.not_anonymous())
    @expose()
    @error_handler(edit)
    def save_user(self, **kw):
        user = User.by_user_name(kw['user']['text'])
        if user is None:
            flash(_(u"Invalid user %s" % kw['user']['text']))
            redirect("./edit?group_id=%s" % kw['group_id'])
        group = Group.by_id(kw['group_id'])

        if not group.can_modify_membership(identity.current.user):
            flash(_(u'You are not an owner of group %s' % group))
            redirect('../groups/mine')

        if user not in group.users:
            group.users.append(user)
            activity = GroupActivity(identity.current.user, u'WEBUI', u'Added', u'User', u"", user.user_name)
            group.activity.append(activity)
            mail.group_membership_notify(user, group,
                                         agent=identity.current.user,
                                         action='Added')
            flash( _(u"OK") )
            redirect("./edit?group_id=%s" % kw['group_id'])
        else:
            flash( _(u"User %s is already in Group %s" %(user.user_name, group.group_name)))
            redirect("./edit?group_id=%s" % kw['group_id'])

    @expose(template="bkr.server.templates.grid_add")
    @paginate('list', default_order='group_name', limit=20)
    def index(self, *args, **kw):
        template_data = self.groups(user=identity.current.user, *args, **kw)
        template_data['grid'] = myPaginateDataGrid(fields=template_data['grid_fields'])
        template_data['addable'] = True
        return template_data

    @expose(template="bkr.server.templates.admin_grid")
    @paginate('list', default_order='group_name', limit=20)
    @identity.require(identity.in_group('admin'))
    def admin(self, *args, **kw):
        # XXX Look at whether this can be removed and instead use mine()
        groups = self.process_search(*args, **kw)
        template_data = self.groups(groups, identity.current.user, *args, **kw)
        template_data['grid_fields'].append((' ',
            lambda x: self.delete_link.display(dict(group_id=x.group_id),
                                               action=url('remove'),
                                               action_text='Remove (-)')))
        groups_grid = myPaginateDataGrid(fields=template_data['grid_fields'])
        template_data['grid'] = groups_grid

        alpha_nav_data = set([elem.group_name[0].capitalize() for elem in groups])
        nav_bar = self._build_nav_bar(alpha_nav_data,'group')
        template_data['alpha_nav_bar'] = nav_bar
        template_data['addable'] = True
        return template_data


    @expose(template="bkr.server.templates.admin_grid")
    @identity.require(identity.not_anonymous())
    @paginate('list', default_order='group_name', limit=20)
    def mine(self,*args,**kw):
        current_user = identity.current.user
        groups = Group.by_user(current_user)
        template_data = self.groups(groups,current_user,*args,**kw)
        template_data['title'] = 'My Groups'
        template_data['grid_fields'].append((' ',
            lambda x: self.delete_link.display(dict(id=x.group_id),
                                               action=url('remove'),
                                               action_text='Remove (-)')))
        groups_grid = myPaginateDataGrid(fields=template_data['grid_fields'])
        template_data['grid'] = groups_grid

        alpha_nav_data = set([elem.group_name[0].capitalize() for elem in groups])
        nav_bar = self._build_nav_bar(alpha_nav_data,'group')
        template_data['alpha_nav_bar'] = nav_bar
        template_data['addable'] = True
        return template_data

    def show_permissions(self):
        grid = widgets.DataGrid(fields=[('Permissions', lambda x: x.permission_name),
            (' ', lambda x: make_fake_link('','remove_permission_%s' % x.permission_id, 'Remove (-)'))])
        grid.name = 'group_permission_grid'
        return grid

    def groups(self, groups=None, user=None, *args,**kw):
        if groups is None:
            groups = session.query(Group)

        def get_groups(x):
            try:
                if x.can_edit(identity.current.user):
                    return make_edit_link(x.group_name,x.group_id)
                else:
                    return make_link('group_members?group_id=%s' % x.group_id, x.group_name)
            except AttributeError:
                return make_link('group_members?group_id=%s' % x.group_id, x.group_name)

        def get_sys(x):
            if len(x.systems):
                return make_link('systems?group_id=%s' % x.group_id, u'System count: %s' % len(x.systems))
            else:
                return 'System count: 0'

        group_name = ('Group Name', get_groups)
        systems = ('Systems', get_sys)
        display_name = ('Display Name', lambda x: x.display_name)
        grid_fields =  [group_name, display_name, systems]
        return_dict = dict(title=u"Groups",
                           grid_fields = grid_fields,
                           object_count = groups.count(),
                           search_bar = None,
                           search_widget = self.search_widget_form,
                           list = groups)

        return return_dict

    @identity.require(identity.not_anonymous())
    @expose()
    def removeUser(self, group_id=None, id=None, **kw):
        group = Group.by_id(group_id)
        group_owners = group.owners()

        if not group.can_modify_membership(identity.current.user):
            flash(_(u'You are not an owner of group %s' % group))
            redirect('../groups/mine')

        if int(id) == group_owners.pop() and not group_owners:
            flash(_(u'You are the only owner of group %s. Cannot remove' % group))
            redirect('../groups/edit?group_id=%s' % group_id)

        groupUsers = group.users
        for user in groupUsers:
            if user.user_id == int(id):
                group.users.remove(user)
                removed = user
                activity = GroupActivity(identity.current.user, u'WEBUI', u'Removed', u'User', removed.user_name, u"")
                group.activity.append(activity)
                mail.group_membership_notify(user, group,
                                             agent=identity.current.user,
                                             action='Removed')
                flash( _(u"%s Removed" % removed.display_name))
                redirect("../groups/edit?group_id=%s" % group_id)
        flash( _(u"No user %s in group %s" % (id, removed.display_name)))
        raise redirect("../groups/edit?group_id=%s" % group_id)

    @identity.require(identity.not_anonymous())
    @expose()
    @restrict_http_method('post')
    def removeSystem(self, group_id=None, id=None, **kw):
        group = Group.by_id(group_id)

        if not group.can_edit(identity.current.user):
            flash(_(u'You are not an owner of group %s' % group))
            redirect('../groups/mine')

        groupSystems = group.systems
        for system in groupSystems:
            if system.id == int(id):
                group.systems.remove(system)
                removed = system
                activity = GroupActivity(identity.current.user, u'WEBUI', u'Removed', u'System', removed.fqdn, u"")
                sactivity = SystemActivity(identity.current.user, u'WEBUI', u'Removed', u'Group', group.display_name, u"")
                group.activity.append(activity)
                system.activity.append(sactivity)
        flash( _(u"%s Removed" % removed.fqdn))
        raise redirect("./edit?group_id=%s" % group_id)

    @identity.require(identity.not_anonymous())
    @expose()
    def remove(self, **kw):
        group = Group.by_id(kw['group_id'])

        if not group.can_edit(identity.current.user):
            flash(_(u'You are not an owner of group %s' % group))
            redirect('../groups/mine')

        session.delete(group)
        activity = Activity(identity.current.user, u'WEBUI', u'Removed', u'Group', group.display_name, u"")
        session.add(activity)
        for system in group.systems:
            SystemActivity(identity.current.user, u'WEBUI', u'Removed', u'Group', group.display_name, u"", object=system)
        flash( _(u"%s deleted") % group.display_name )
        raise redirect(".")

    @expose(format='json')
    def get_group_users(self, group_id=None, *args, **kw):
        try:
            group = Group.by_id(group_id)
        except NoResultFound:
            log.exception('Group id %s is not a valid group id' % group_id)
            response.status = 403
            return ['Invalid Group Id']

        users = group.users
        return [(user.user_id, user.display_name) for user in users]

    @expose(format='json')
    def get_group_systems(self, group_id=None, *args, **kw):
        try:
            group = Group.by_id(group_id)
        except NoResultFound:
            log.exception('Group id %s is not a valid group id' % group_id)
            response.status = 403
            return ['Invalid Group Id']

        systems = group.systems
        return [(system.id, system.fqdn) for system in systems]

    # XML-RPC method for creating a group
    @identity.require(identity.not_anonymous())
    @expose(format='json')
    def create(self, kw):
        """
        Creates a new group.

        The *kw* argument must be an XML-RPC structure (dict)
        specifying the following keys:

            'group_name'
                 Group name (maximum 16 characters)
            'display_name'
                 Group display name
            'ldap'
                 Populate users from LDAP (True/False)

        Returns a message whether the group was successfully created or
        raises an exception on failure.

        """
        display_name = kw.get('display_name')
        group_name = kw.get('group_name')
        ldap = kw.get('ldap')
        password = kw.get('root_password')

        if ldap and not identity.current.user.is_admin():
            raise BX(_(u'Only admins can create LDAP groups'))
        try:
            group = Group.by_name(group_name)
        except NoResultFound:
            group = Group()
            session.add(group)
            activity = Activity(identity.current.user, u'XMLRPC', u'Added', u'Group', u"", kw['display_name'] )
            group.display_name = display_name
            group.group_name = group_name
            group.ldap = ldap
            group.root_password = password
            user = identity.current.user

            if not ldap:
                group.user_group_assocs.append(UserGroup(user=user, is_owner=True))
                group.activity.append(GroupActivity(user, service=u'XMLRPC',
                    action=u'Added', field_name=u'User',
                    old_value=None, new_value=user.user_name))
                group.activity.append(GroupActivity(user, service=u'XMLRPC',
                    action=u'Added', field_name=u'Owner',
                    old_value=None, new_value=user.user_name))

            if group.ldap:
                group.refresh_ldap_members()
            return 'Group created: %s.' % group_name
        else:
            raise BX(_(u'Group already exists: %s.' % group_name))

    # XML-RPC method for modifying a group
    @identity.require(identity.not_anonymous())
    @expose(format='json')
    def modify(self, group_name, kw):
        """
        Modifies an existing group. You must be an owner of a group to modify any details.

        :param group_name: An existing group name
        :type group_name: string

        The *kw* argument must be an XML-RPC structure (dict)
        specifying the following keys:

            'group_name'
                 New group name (maximum 16 characters)
            'display_name'
                 New group display name
            'add_member'
                 Add user (username) to the group
            'remove_member'
                 Remove an existing user (username) from the group

        Returns a message whether the group was successfully modified or
        raises an exception on failure.

        """
        # if not called from the bkr group-modify
        if not kw:
            raise BX(_('Please specify an attribute to modify.'))

        try:
            group = Group.by_name(group_name)
        except NoResultFound:
            raise BX(_(u'Group does not exist: %s.' % group_name))

        user = identity.current.user
        if not group.can_edit(user):
            raise BX(_('You are not an owner of group %s' % group_name))

        group.set_display_name(user, u'XMLRPC', kw.get('display_name', None))
        group.set_name(user, u'XMLRPC', kw.get('group_name', None))

        if kw.get('add_member', None):
            username = kw.get('add_member')
            user = User.by_user_name(username)
            if user is None:
                raise BX(_(u'User does not exist %s' % username))

            if user not in group.users:
                group.users.append(user)
                activity = GroupActivity(identity.current.user, u'XMLRPC',
                                            action=u'Added',
                                            field_name=u'User',
                                            old_value=u"", new_value=username)
                group.activity.append(activity)
                mail.group_membership_notify(user, group,
                                                agent = identity.current.user,
                                                action='Added')
            else:
                raise BX(_(u'User %s is already in group %s' % (username, group.group_name)))

        if kw.get('remove_member', None):
            username = kw.get('remove_member')
            user = User.by_user_name(username)

            if user is None:
                raise BX(_(u'User does not exist %s' % username))

            if user not in group.users:
                raise BX(_(u'No user %s in group %s' % (username, group.group_name)))
            else:
                group_owners = group.owners()
                if user.user_id == group_owners.pop() and not group_owners:
                    raise BX(_(u'You are the only owner of group %s. Cannot remove' % group))

                groupUsers = group.users
                for usr in groupUsers:
                    if usr.user_id == user.user_id:
                        group.users.remove(usr)
                        removed = user
                        activity = GroupActivity(identity.current.user, u'XMLRPC',
                                                    action=u'Removed',
                                                    field_name=u'User',
                                                    old_value=removed.user_name,
                                                    new_value=u"")
                        group.activity.append(activity)
                        mail.group_membership_notify(user, group,
                                                        agent=identity.current.user,
                                                        action='Removed')
                        break

        #dummy success return value
        return ['1']

    # XML-RPC method for listing a group's members
    @identity.require(identity.not_anonymous())
    @expose(format='json')
    def members(self, group_name):
        """
        List the members of an existing group.

        :param group_name: An existing group name
        :type group_name: string

        Returns a list of the members (a dictionary containing each
        member's username, email, and whether the member is an owner
        or not).

        """
        try:
            group = Group.by_name(group_name)
        except NoResultFound:
            raise BX(_(u'Group does not exist: %s.' % group_name))

        users=[]
        for u in group.users:
            user={}
            user['username']=u.user_name
            user['email'] = u.email_address
            if group.has_owner(u):
                user['owner'] = True
            else:
                user['owner'] = False
            users.append(user)

        return users

# for sphinx
groups = Groups
