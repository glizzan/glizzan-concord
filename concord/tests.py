import json
from decimal import Decimal
import time
from collections import namedtuple
from unittest import skip
from datetime import timedelta

from django.utils import timezone
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from concord.actions.models import Action
from concord.actions.utils import Changes, Client
from concord.permission_resources.models import PermissionsItem
from concord.conditionals.models import ApprovalCondition
from concord.resources.models import Resource, Item
from concord.actions import template_library
from concord.actions.text_utils import condition_template_to_text
from concord.communities.state_changes import AddLeadershipConditionStateChange
from concord.permission_resources.state_changes import AddPermissionConditionStateChange


class DataTestCase(TestCase):

    @classmethod
    def setUpTestData(self):

        # Create a single set of users for all tests

        class Users(object):
            pass

        self.users = Users()

        # let's go woso
        self.users.pinoe = User.objects.create(username="meganrapinoe")
        self.users.rose = User.objects.create(username="roselavelle")
        self.users.tobin = User.objects.create(username="tobinheath")
        self.users.christen = User.objects.create(username="christenpress")
        self.users.crystal = User.objects.create(username="crystaldunn")
        self.users.jmac = User.objects.create(username="jessicamacdonald")
        self.users.sonny = User.objects.create(username="emilysonnett")
        self.users.jj = User.objects.create(username="julieertz")
        self.users.sully = User.objects.create(username="andisullivan")
        self.users.aubrey = User.objects.create(username="aubreybledsoe")
        self.users.hao = User.objects.create(username="heatheroreilly")

    def display_last_actions(self, number=10):
        """Helper method which shows the last N actions to be created, useful for debugging."""
        actions = Action.objects.all().order_by('-id')[:number]
        for action in reversed(actions):
            print(action)


class ResourceModelTests(DataTestCase):

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)

    def test_create_resource(self):
        """
        Test creation of simple resource through client, and its method
        get_unique_id.
        """
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.assertEquals(resource.get_unique_id(), "resources_resource_1")

    def test_add_item_to_resource(self):
        """
        Test creation of item and addition to resource.
        """
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.Resource.set_target(target=resource)
        action, item = self.client.Resource.add_item(item_name="Equal Pay")
        self.assertEquals(item.get_unique_id(), "resources_item_1")

    def test_remove_item_from_resource(self):
        """
        Test removal of item from resource.
        """
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.Resource.set_target(target=resource)
        action, item = self.client.Resource.add_item(item_name="Equal Pay")
        self.assertEquals(resource.get_items(), ["Equal Pay"])
        self.client.Resource.remove_item(item_pk=item.pk)
        self.assertEquals(resource.get_items(), [])


class PermissionResourceModelTests(DataTestCase):

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)

    def test_add_permission_to_resource(self):
        """
        Test addition of permisssion to resource.
        """
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(
            permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.pinoe.pk])
        items = self.client.PermissionResource.get_permissions_on_object(target_object=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for concord.resources.state_changes.AddItemStateChange on Resource object (1))')

    def test_remove_permission_from_resource(self):
        """
        Test removal of permission from resource.
        """
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(
            permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.pinoe.pk])
        items = self.client.PermissionResource.get_permissions_on_object(target_object=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for concord.resources.state_changes.AddItemStateChange on Resource object (1))')
        self.client.PermissionResource.remove_permission(item_pk=permission.pk)
        items = self.client.PermissionResource.get_permissions_on_object(target_object=resource)
        self.assertEquals(list(items), [])


class PermissionSystemTest(DataTestCase):
    """
    The previous two sets of tests use the default permissions setting for the items
    they're modifying.  For individually owned objects, this means that the owner can do 
    whatever they want and no one else can do anything.  This set of tests looks at the basic 
    functioning of the permissions system including permissions set on permissions.
    """

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)

    def test_permissions_system(self):
        """
        Create a resource and add a specific permission for a non-owner actor.
        """
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(
            permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        items = self.client.PermissionResource.get_permissions_on_object(target_object=resource)
        self.assertEquals(items.first().get_name(), 
            'Permission 1 (for concord.resources.state_changes.AddItemStateChange on Resource object (1))')

        # Now the non-owner actor (Rose) takes the permitted action on the resource
        self.roseClient = Client(actor=self.users.rose, target=resource)
        action, item = self.roseClient.Resource.add_item(item_name="Test New")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Test New")

    def test_recursive_permission(self):
        """
        Tests setting permissions on permission.
        """

        # Pinoe creates a resource and adds a permission for Rose to the resource.
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.rose.pk])

        # Tobin can't add an item to this resource because she's not the owner nor specified in
        # the permission.
        self.tobinClient = Client(actor=self.users.tobin, target=resource)
        action, item = self.tobinClient.Resource.add_item(item_name="Tobin's item")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Pinoe adds a permission on the permission which Tobin does have.
        self.client.PermissionResource.set_target(target=permission)
        action, rec_permission = self.client.PermissionResource.add_permission(permission_type=Changes().Permissions.AddPermission,
            permission_actors=[self.users.tobin.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Tobin still cannot make the original change because she does not have *that* permission.
        action, item = self.tobinClient.Resource.add_item(item_name="Tobin's item")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        
        # But Tobin CAN make the second-level change.
        self.tobinClient.PermissionResource.set_target(target=permission)
        action, permission = self.tobinClient.PermissionResource.add_permission(permission_type=Changes().Permissions.AddPermission,
            permission_actors=[self.users.rose.pk])        
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_multiple_specific_permission(self):
        """Tests that when multiple permissions are set, they're handled in an OR fashion."""

        # Pinoe creates a resource and adds a permission to the resource.
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.christen.pk])

        # Then she adds another permission with different actors/roles.
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.tobin.pk])

        # Both of the actors specified can do the thing.

        self.christenClient = Client(actor=self.users.christen, target=resource)
        action, item = self.christenClient.Resource.add_item(item_name="Christen Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Christen Test")  

        self.tobinClient = Client(actor=self.users.tobin, target=resource)
        action, item = self.tobinClient.Resource.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Tobin Test")

    def test_multiple_specific_permission_with_conditions(self):
        """test multiple specific permissions with conditionals"""
        
        # Pinoe creates a resource and adds a permission to the resource.
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.christen.pk])

        # Then she adds another permission with different actors/roles.
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.tobin.pk])

        # Then she adds a condition to the second one
        permission_data = [
            { "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.pinoe.pk]}
        ]
        action, condition = self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk,
            condition_type="approvalcondition", condition_data=None, permission_data=permission_data)

        # The first (Christen) is accepted while the second (Tobin) has to wait

        self.christenClient = Client(actor=self.users.christen, target=resource)
        action, item = self.christenClient.Resource.add_item(item_name="Christen Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Christen Test")  

        self.tobinClient = Client(actor=self.users.tobin, target=resource)
        action, item = self.tobinClient.Resource.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")
        self.assertEquals(item, None)

    def test_inverse_permission(self):
        """Tests that when inverse toggle is flipped, permissions match appropriately."""

        # Pinoe creates a resource and adds a permission to the resource.
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.jj.pk])

        # JJ can use the permission
        self.jjClient = Client(actor=self.users.jj, target=resource)
        action, item = self.jjClient.Resource.add_item(item_name="JJ Ertz's Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "JJ Ertz's Test")  

        # Pinoe toggles the permission
        action, result = self.client.PermissionResource.change_inverse_field_of_permission(change_to=True, 
            permission_pk=permission.pk)
        permission.refresh_from_db()
        self.assertEquals(permission.inverse, True)

        # JJ can no longer use the permission
        action, item = self.jjClient.Resource.add_item(item_name="JJ Test #2")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(item, None) 

        # but anyone who is not JJ can
        self.tobinClient = Client(actor=self.users.tobin, target=resource)
        action, item = self.tobinClient.Resource.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Tobin Test")

    def test_nested_object_permission_no_conditions(self):

        # Pinoe creates a group, then a resource, then transfers ownership of resource to group
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.Community.set_target(self.instance)
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.Resource.set_target(resource)
        self.client.Resource.change_owner_of_target(self.instance)

        # She sets a permission on the resource and it works, blocking Tobin from adding an item
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.christen.pk])
        self.tobinClient = Client(actor=self.users.tobin, target=resource)
        action, item = self.tobinClient.Resource.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(item, None)

        # She sets a permission on the group that does let Tobin add item, now it works
        self.client.PermissionResource.set_target(target=self.instance)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.tobin.pk])
        
        self.tobinClient = Client(actor=self.users.tobin, target=resource)
        action, item = self.tobinClient.Resource.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_nested_object_permission_with_conditions(self):
        
        # Pinoe creates a group, then a resource, then transfers ownership of resource to group
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.Community.set_target(self.instance)
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.Resource.set_target(resource)
        self.client.Resource.change_owner_of_target(self.instance)

        # She sets permissions on the resource and on the group, both of which let Tobin add an item
        self.client.PermissionResource.set_target(target=resource)
        action, resource_permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.tobin.pk])
        self.client.PermissionResource.set_target(target=self.instance)
        action, group_permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.tobin.pk])

        # She adds a condition to the one on the resource
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.crystal.pk]}]
        action, result = self.client.PermissionResource.add_condition_to_permission(permission_pk=resource_permission.pk, 
            condition_type="approvalcondition", permission_data=permission_data, condition_data=None)

        # Tobin adds an item and it works without setting off the conditional
        self.tobinClient = Client(actor=self.users.tobin, target=resource)
        action, item = self.tobinClient.Resource.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # She adds a condition to the group, now Tobin has to wait
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.crystal.pk]}]
        action, result = self.client.PermissionResource.add_condition_to_permission(permission_pk=group_permission.pk, 
            condition_type="approvalcondition", permission_data=permission_data, condition_data=None)
        action, item = self.tobinClient.Resource.add_item(item_name="Tobin Test 2")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")

    def test_anyone_permission_toggle(self):

        # Create a group with members, give members permission to change the group name
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.Community.set_target(self.instance)
        self.client.Community.add_members([self.users.rose.pk, self.users.crystal.pk,
            self.users.tobin.pk])
        self.client.PermissionResource.set_target(self.instance)
        action, result = self.client.PermissionResource.add_permission(permission_type=Changes().Communities.ChangeName,
            permission_roles=['members'])
        self.target_permission = result

        # Test someone in the group can do the thing
        self.roseClient = Client(actor=self.users.rose, target=self.instance)
        action, result = self.roseClient.Community.change_name(new_name="USWNT!!!!")
        self.assertEquals(action.status, "implemented")
        self.assertEquals(self.instance.name, "USWNT!!!!")

        # Test that another user, Sonny, who is not in the group, can't do the thing
        self.sonnyClient = Client(actor=self.users.sonny, target=self.instance)
        action, result = self.sonnyClient.Community.change_name(new_name="USWNT????")
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.instance.name, "USWNT!!!!")

        # Now we give that permission to "anyone"
        action, result = self.client.PermissionResource.give_anyone_permission(permission_pk=self.target_permission.pk)

        # Our non-member can do the thing now!
        action, result = self.sonnyClient.Community.change_name(new_name="USWNT????")
        self.assertEquals(action.status, "implemented")
        self.assertEquals(self.instance.name, "USWNT????")

        # Let's toggle anyone back to disabled
        action, result = self.client.PermissionResource.remove_anyone_from_permission(permission_pk=self.target_permission.pk)
        
        # Once again our non-member can no longer do the thing
        action, result = self.sonnyClient.Community.change_name(new_name="USWNT :D :D :D")
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.instance.name, "USWNT????")

    def test_condition_form_generation(self):

         # Pinoe creates a resource and adds a permission to the resource and a condition to the permission.
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.tobin.pk])
        permission_data = [
            {"permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.pinoe.pk]}
        ]
        action, condition = self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk,
            condition_type="approvalcondition", condition_data=None, permission_data=permission_data)

        permission = PermissionsItem.objects.get(pk=permission.pk) #refresh
        self.assertEquals(permission.get_condition_data(info="basic"),
            {'type': 'ApprovalCondition', 'display_name': 'Approval Condition', 
            'how_to_pass': 'one person needs to approve this action'})
        self.assertEquals(permission.get_condition_data(info="fields"), 
            {'self_approval_allowed': 
                {'display': 'Can individuals approve their own actions?', 'field_name': 'self_approval_allowed', 
                'type': 'BooleanField', 'required': '', 'value': False}, 
            'approve_roles': 
                {'display': 'Roles who can approve', 'type': 'PermissionRoleField', 'required': False, 
                'value': None, 'field_name': 'approve_roles', 'full_name': 'concord.conditionals.state_changes.ApproveStateChange'}, 
            'approve_actors': 
                {'display': 'People who can approve', 'type': 'PermissionActorField', 'required': False, 'value': [1], 
                'field_name': 'approve_actors', 'full_name': 'concord.conditionals.state_changes.ApproveStateChange'}, 
            'reject_roles': 
                {'display': 'Roles who can reject', 'type': 'PermissionRoleField', 'required': False, 'value': None, 
                'field_name': 'reject_roles', 'full_name': 'concord.conditionals.state_changes.RejectStateChange'}, 
            'reject_actors': 
                {'display': 'People who can reject', 'type': 'PermissionActorField', 'required': False, 'value': None, 
                'field_name': 'reject_actors', 'full_name': 'concord.conditionals.state_changes.RejectStateChange'}})


class ConditionSystemTest(DataTestCase):

    def test_add_permission_to_condition_state_change(self):
        permission = PermissionsItem()
        permission_data = [{ "permission_type": Changes().Conditionals.AddVote, 
            "permission_actors": [self.users.crystal.pk, self.users.jmac.pk] }]
        change = AddPermissionConditionStateChange(permission_pk=1, condition_type="votecondition", condition_data=None,
            permission_data=permission_data)
        mock_actions = change.generate_mock_actions(actor=self.users.pinoe, permission=permission)
        self.assertEquals(len(mock_actions), 2)
        self.assertEquals(mock_actions[0].change.get_change_type(), Changes().Conditionals.SetConditionOnAction)
        self.assertEquals(mock_actions[1].change.get_change_type(), Changes().Permissions.AddPermission)     
        self.assertEquals(mock_actions[0].target, "{{trigger_action}}")  
        self.assertEquals(mock_actions[1].change.permission_actors, [self.users.crystal.pk, self.users.jmac.pk])

    def test_add_leadership_condition_state_change(self):
        self.client = Client(actor=self.users.pinoe)
        community = self.client.Community.create_community(name="Test community")
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_roles": ["members"] }]
        change = AddLeadershipConditionStateChange(condition_type="approvalcondition", condition_data=None, 
            permission_data=permission_data, leadership_type="governor")
        mock_actions = change.generate_mock_actions(actor=self.users.pinoe, target=community)
        self.assertEquals(len(mock_actions), 2)
        self.assertEquals(mock_actions[0].change.get_change_type(), Changes().Conditionals.SetConditionOnAction)
        self.assertEquals(mock_actions[1].change.get_change_type(), Changes().Permissions.AddPermission)        
        self.assertEquals(mock_actions[0].target, "{{trigger_action}}")  
        self.assertEquals(mock_actions[1].change.permission_roles, ["members"])

    def test_condition_template_text_util_with_vote_condition(self):
        permission = PermissionsItem()
        permission_data = [{ "permission_type": Changes().Conditionals.AddVote, 
            "permission_actors": [self.users.crystal.pk, self.users.jmac.pk] }]
        change = AddPermissionConditionStateChange(permission_pk=1, condition_type="votecondition", condition_data=None,
            permission_data=permission_data)
        mock_actions = change.generate_mock_actions(actor=self.users.pinoe, permission=permission)
        text = condition_template_to_text(mock_actions[0], mock_actions[1:])
        self.assertEquals(text, "on the condition that individuals 5 and 6 vote")

    def test_condition_template_text_util_with_approval_condition(self):
        self.client = Client(actor=self.users.pinoe)
        community = self.client.Community.create_community(name="Test community")
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_roles": ["members"] },
            { "permission_type": Changes().Conditionals.Reject, "permission_actors": [self.users.crystal.pk]}]
        change = AddLeadershipConditionStateChange(condition_type="approvalcondition", condition_data=None, 
            permission_data=permission_data, leadership_type="governor")
        mock_actions = change.generate_mock_actions(actor=self.users.pinoe, target=community)
        text = condition_template_to_text(mock_actions[0], mock_actions[1:])
        self.assertEquals(text, "on the condition that those with role members approve and individual 5 does not reject")


class ConditionalsTest(DataTestCase):

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)
        self.target = self.client.Resource.create_resource(name="Go USWNT!")
        from concord.resources.state_changes import ChangeResourceNameStateChange
        self.action = Action.objects.create(actor=self.users.sully, target=self.target,
            change=ChangeResourceNameStateChange(new_name="Go Spirit!"))
    
    def test_vote_conditional(self):

        # First Pinoe creates a resource
        resource = self.client.Resource.create_resource(name="Go USWNT!")

        # Then she adds a permission that says that Rose can add items.
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        
        # But she places a vote condition on the permission
        permission_data = [{ "permission_type": Changes().Conditionals.AddVote, 
            "permission_actors": [self.users.jmac.pk, self.users.crystal.pk] }]
        self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk, condition_type="votecondition", 
            permission_data=permission_data)

        # Rose tries to add an item, triggering the condition
        self.client.Resource.set_actor(actor=self.users.rose)
        self.client.Resource.set_target(target=resource)
        action, result = self.client.Resource.add_item(item_name="Rose's item")

        # We get the vote condition
        crystalClient = Client(actor=self.users.crystal)
        item = crystalClient.Conditional.get_condition_item_given_action_and_source(action_pk=action.pk, 
            source_id="perm_"+str(permission.pk))
        vote_condition = crystalClient.Conditional.get_condition_as_client(condition_type="VoteCondition", pk=item.pk)

        # Now Crystal and JMac can vote but Rose can't

        action,result = vote_condition.vote(vote="yea")
        self.assertDictEqual(vote_condition.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 0 })

        vote_condition.set_actor(actor=self.users.jmac)
        action, result = vote_condition.vote(vote="abstain")
        self.assertDictEqual(vote_condition.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 1})

        vote_condition.set_actor(actor=self.users.rose)
        vote_condition.vote(vote="abstain")
        self.assertDictEqual(vote_condition.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 1})         

    def test_approval_conditional(self):
        """
        Tests that changes to a resource require approval from a specific person,
        check that that person can approve the change and others can't.
        """

        # First Pinoe creates a resource
        resource = self.client.Resource.create_resource(name="Go USWNT!")

        # Then she adds a permission that says that Rose can add items.
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        
        # But she places a condition on the permission that Rose has to get
        # approval (without specifying permissions, so it uses the default governing/foundational.
        self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition")

        # Now when Sonny tries to add an item she is flat out rejected
        self.client.Resource.set_actor(actor=self.users.sonny)
        self.client.Resource.set_target(target=resource)
        action, item = self.client.Resource.add_item(item_name="Saucy Sonny's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # When Rose tries to add an item it is stuck waiting
        self.client.Resource.set_actor(actor=self.users.rose)
        rose_action, item = self.client.Resource.add_item(item_name="Rose's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "waiting")

        # Get the conditional action
        conditional_action = self.client.Conditional.get_condition_item_given_action_and_source(action_pk=rose_action.pk,
            source_id="perm_"+str(permission.pk))

        # Sonny tries to approve it and fails.  Sonny you goof.
        sonnyClient = Client(target=conditional_action, actor=self.users.sonny, limit_to=["ApprovalCondition"])
        action, result = sonnyClient.ApprovalCondition.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(resource.get_items(), [])

        # Now Pinoe approves it
        self.client.ApprovalCondition.set_target(target=conditional_action)
        action, result = self.client.ApprovalCondition.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
    
        # And Rose's item has been added
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "implemented")
        self.assertEquals(resource.get_items(), ["Rose's item"])

    def test_add_and_remove_condition_on_permission(self):

        # Pinoe creates a resource and sets a permission and a condition on the permission
        resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, 
            "permission_actors" : [self.users.crystal.pk]}]
        self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition", 
            permission_data=permission_data)

        # When Rose tries to add an item it is stuck waiting
        self.client.Resource.set_actor(actor=self.users.rose)
        self.client.Resource.set_target(target=resource)
        rose_action, item = self.client.Resource.add_item(item_name="Rose's item")
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "waiting")

        # Now Pinoe removes it
        self.client.PermissionResource.remove_condition_from_permission(permission_pk=permission.pk)

        # When Rose tries again, it passes
        self.client.Resource.set_actor(actor=self.users.rose)
        self.client.Resource.set_target(target=resource)
        rose_action, item = self.client.Resource.add_item(item_name="Rose's item")
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "implemented")
        
    def test_approval_conditional_with_second_order_permission(self):
        """
        Mostly the same as above, but instead of using the default permission on
        the conditional action, we specify that someone specific has to approve
        the action.
        """

        # First we have Pinoe create a resource
        resource = self.client.Resource.create_resource(name="Go USWNT!")

        # Then she adds a permission that says that Rose can add items.
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        
        # But she places a condition on the permission that Rose has to get
        # approval.  She specifies that *Crystal* has to approve it.
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, 
            "permission_actors" : [self.users.crystal.pk]}]
        self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition", 
            permission_data=permission_data)

        # When Rose tries to add an item it is stuck waiting
        self.client.Resource.set_actor(actor=self.users.rose)
        self.client.Resource.set_target(target=resource)
        rose_action, item = self.client.Resource.add_item(item_name="Rose's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "waiting")

        # Get the conditional action
        conditional_action = self.client.Conditional.get_condition_item_given_action_and_source(action_pk=rose_action.pk,
            source_id="perm_"+ str(permission.pk))

        # Now Crystal approves it
        crystalClient = Client(target=conditional_action, actor=self.users.crystal)
        action, result = crystalClient.ApprovalCondition.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
    
        # And Rose's item has been added
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "implemented")
        self.assertEquals(resource.get_items(), ["Rose's item"])

    def test_multiple_permissions_on_condition(self):

        # First we have Pinoe create a resource
        resource = self.client.Resource.create_resource(name="Go USWNT!")

        # Then she adds a permission that says that Rose can add items.
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        
        # But she places a condition on the permission that Rose has to get
        # approval.  She specifies that *Crystal* has to approve it.  She also 
        # specifies that Andi Sullivan can reject it.
        permission_data = [
            { "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.crystal.pk] },
            { "permission_type": Changes().Conditionals.Reject, "permission_actors": [self.users.sully.pk] }
        ]
        action, result = self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition", 
            permission_data=permission_data)

        # When Rose tries to add an item, Crystal can approve it
        self.client.Resource.set_actor(actor=self.users.rose)
        self.client.Resource.set_target(target=resource)
        rose_action_one, item = self.client.Resource.add_item(item_name="Rose's first item")
        conditional_action = self.client.Conditional.get_condition_item_given_action_and_source(action_pk=rose_action_one.pk,
            source_id="perm_"+str(permission.pk))
        crystalClient = Client(target=conditional_action, actor=self.users.crystal)
        action, result = crystalClient.ApprovalCondition.approve()
    
        # When Rose tries to add an item, Andi Sullivan can reject it
        rose_action_two, item = self.client.Resource.add_item(item_name="Rose's second item")
        conditional_action = self.client.Conditional.get_condition_item_given_action_and_source(action_pk=rose_action_two.pk,
            source_id="perm_"+str(permission.pk))
        sullyClient = Client(target=conditional_action, actor=self.users.sully)
        action, result = sullyClient.ApprovalCondition.reject()

        # We see Rose's first item but not her second has been added
        self.assertEquals(Action.objects.get(pk=rose_action_one.pk).status, "implemented")
        self.assertEquals(Action.objects.get(pk=rose_action_two.pk).status, "rejected")
        self.assertEquals(resource.get_items(), ["Rose's first item"])

        # Rose tries one more time - Andi can't approve and Crystal can't reject, so the action is waiting
        rose_action_three, item = self.client.Resource.add_item(item_name="Rose's third item")        
        conditional_action = self.client.Conditional.get_condition_item_given_action_and_source(action_pk=rose_action_three.pk,
            source_id="perm_"+str(permission.pk))
        crystalClient.ApprovalCondition.set_target(target=conditional_action)
        action, result = crystalClient.ApprovalCondition.reject()
        sullyClient.ApprovalCondition.set_target(target=conditional_action)
        action, result = sullyClient.ApprovalCondition.approve()
        self.assertEquals(Action.objects.get(pk=rose_action_three.pk).status, "waiting")


class BasicCommunityTest(DataTestCase):

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)

    def test_create_community(self):
        community = self.client.Community.create_community(name="A New Community")
        self.assertEquals(community.get_unique_id(), "communities_community_1")
        self.assertEquals(community.name, "A New Community")
    
    def test_community_is_itself_collectively_owned(self):
        community = self.client.Community.create_community(name="A New Community")
        self.assertEquals(community.get_owner(), community)

    def test_community_collectively_owns_resource(self):
        community = self.client.Community.create_community(name="A New Community")
        resource = self.client.Resource.create_resource(name="A New Resource")
        self.assertEquals(resource.get_owner().name, "meganrapinoe's Default Community")
        self.client.Resource.set_target(target=resource)
        self.client.Resource.change_owner_of_target(new_owner=community)
        self.assertEquals(resource.get_owner().name, "A New Community")

    def test_change_name_of_community(self):
        community = self.client.Community.create_community(name="A New Community")
        self.client.Community.set_target(target=community)
        action, result = self.client.Community.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(community.name, "A Newly Named Community")

    def test_reject_change_name_of_community_from_nongovernor(self):
        community = self.client.Community.create_community(name="A New Community")
        self.client.Community.set_target(target=community)
        self.client.Community.set_actor(actor=self.users.jj)
        action, result = self.client.Community.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(community.name, "A New Community")

    def test_change_name_of_community_owned_resource(self):
        # SetUp
        community = self.client.Community.create_community(name="A New Community")
        resource = self.client.Resource.create_resource(name="A New Resource")
        self.client.Resource.set_target(target=resource)
        action, result = self.client.Resource.change_owner_of_target(new_owner=community)
        self.assertEquals(resource.get_owner().name, "A New Community")
        # Test
        new_action, result = self.client.Resource.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action.pk).status, "implemented")
        self.assertEquals(resource.name, "A Changed Resource")

    def test_reject_change_name_of_community_owned_resource_from_nongovernor(self):
        # SetUp
        community = self.client.Community.create_community(name="A New Community")
        resource = self.client.Resource.create_resource(name="A New Resource")
        self.client.Resource.set_target(target=resource)
        action, result = self.client.Resource.change_owner_of_target(new_owner=community)
        self.assertEquals(resource.get_owner().name, "A New Community")
        # Test
        self.client.Resource.set_actor(actor=self.users.jj)
        new_action, result = self.client.Resource.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action.pk).status, "rejected")
        self.assertEquals(resource.name, "A New Resource")

    def test_add_permission_to_community_owned_resource_allowing_nongovernor_to_change_name(self):
        
        # SetUp
        community = self.client.Community.create_community(name="A New Community")
        resource = self.client.Resource.create_resource(name="A New Resource")
        self.client.Resource.set_target(target=resource)
        action, result = self.client.Resource.change_owner_of_target(new_owner=community)
        self.assertEquals(resource.get_owner().name, "A New Community")

        # Add  permission for nongovernor to change name
        self.client.PermissionResource.set_target(target=resource)
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.ChangeResourceName,
            permission_actors=[self.users.jj.pk])
        
        # Test - JJ should now be allowed to change name
        self.client.Resource.set_actor(actor=self.users.jj)
        new_action, result = self.client.Resource.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action.pk).status, "implemented")
        self.assertEquals(resource.name, "A Changed Resource")    

        # Test - Governors should still be able to do other things still that are not set in PR
        self.client.Resource.set_actor(actor=self.users.pinoe)
        new_action, result = self.client.Resource.add_item(item_name="Pinoe's item")
        self.assertEquals(resource.get_items(), ["Pinoe's item"])

    def test_add_governor(self):
        community = self.client.Community.create_community(name="A New Community")
        self.client.Community.set_target(community)
        action, result = self.client.Community.add_governor(governor_pk=self.users.crystal.pk)
        self.assertEquals(community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})


class GoverningAuthorityTest(DataTestCase):

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)
        self.community = self.client.Community.create_community(name="A New Community")
        self.client.update_target_on_all(target=self.community)
        self.client.Community.add_members([self.users.sonny.pk])
        self.client.Community.add_governor(governor_pk=self.users.sonny.pk)

    def test_with_conditional_on_governer_decision_making(self):

        # Set conditional on governor decision making.  Only Sonny can approve condition.
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.sonny.pk]}]
        action, result = self.client.Community.add_leadership_condition(
            leadership_type="governor", condition_type="approvalcondition", permission_data=permission_data)
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented") # Action accepted

        # Governor Pinoe does a thing, creates a conditional action to be approved
        action, result = self.client.Community.change_name(new_name="A Newly Named Community")
        # self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")
        # self.assertEquals(self.community.name, "A New Community")
        # conditional_action = self.condClient.get_condition_item_given_action_and_source(action_pk=action.pk,
        #     source_id="governor_"+str(self.community.pk))

        # # Governer Sonny reviews
        # acc = ApprovalConditionClient(target=conditional_action, actor=self.users.sonny)
        # review_action, result = acc.approve()
        # self.assertEquals(Action.objects.get(pk=review_action.pk).status, "implemented")

        # # Now Governor Pinoe's thing passes.
        # self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        # self.community.refresh_from_db()
        # self.assertEquals(self.community.name, "A Newly Named Community")


class FoundationalAuthorityTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create community
        self.community = self.client.Community.create_community(name="A New Community")

        # Create a resource and give ownership to community
        self.resource = self.client.Resource.create_resource(name="A New Resource")
        self.client.Resource.set_target(target=self.resource)
        self.client.Resource.change_owner_of_target(new_owner=self.community)

    def test_foundational_authority_override_on_individually_owned_object(self):

        # Create individually owned resource
        resource = self.client.Resource.create_resource(name="A resource")

        # By default, Aubrey's actions are not successful
        aubreyClient = Client(actor=self.users.aubrey, target=resource)
        action, result = aubreyClient.Resource.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(resource.get_name(), "A resource")

        # Owner adds a specific permission for Aubrey, so Aubrey's action is successful
        self.client.PermissionResource.set_target(resource)
        owner_action, result = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.ChangeResourceName,
            permission_actors=[self.users.aubrey.pk])
        action, result = aubreyClient.Resource.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(resource.get_name(), "Aubrey's resource")

        # Now switch foundational override.
        fp_action, result = self.client.PermissionResource.enable_foundational_permission()

        # Aunrey's actions are no longer successful
        action, result = aubreyClient.Resource.change_name(new_name="A new name for Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(resource.get_name(), "Aubrey's resource")

    def test_foundational_authority_override_on_community_owned_object(self):
        
        # By default, Aubrey's actions are not successful
        aubreyClient = Client(actor=self.users.aubrey, target=self.resource)
        action, result = aubreyClient.Resource.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Owner Pinoe adds a specific permission for Aubrey, Aubrey's action is successful
        self.client.PermissionResource.set_target(self.resource)
        owner_action, result = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.ChangeResourceName,
            permission_actors=[self.users.aubrey.pk])
        action, result = aubreyClient.Resource.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.get_name(), "Aubrey's resource")

        # Now switch foundational override.
        fp_action, result = self.client.PermissionResource.enable_foundational_permission()

        # Aubrey's actions are no longer successful
        action, result = aubreyClient.Resource.change_name(new_name="A new name for Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "Aubrey's resource")

    def test_foundational_authority_override_on_community_owned_object_with_conditional(self):
        
        # Pinoe, Tobin, Christen and JMac are members of the community. 
        self.client.Community.set_target(self.community)
        action, result = self.client.Community.add_members([self.users.tobin.pk, self.users.christen.pk,
            self.users.jmac.pk])
        com_members = self.client.Community.get_members()
        self.assertCountEqual(com_members,
            [self.users.pinoe, self.users.tobin, self.users.christen, self.users.jmac])

        # In this community, all members are owners but for the foundational authority to do
        # anything they must agree via majority vote.
        action, result = self.client.Community.add_owner_role(owner_role="members") # Add member role
        permission_data = [{ "permission_type": Changes().Conditionals.AddVote, "permission_roles": ["members"]}]
        action, result = self.client.Community.add_leadership_condition(
            leadership_type="owner",
            condition_type = "votecondition", 
            condition_data={"voting_period": 1 },
            permission_data=permission_data
        )

        # Christen tries to change the name of the resource but is not successful because it's not something
        # that triggers foundational authority.
        christenClient = Client(actor=self.users.christen, target=self.resource)
        action, result = christenClient.Resource.change_name(new_name="Christen's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Christen tries to switch on foundational override.  This is a foundational change and thus it 
        # enter the foundational pipeline, triggers a vote condition, and generates a vote. Everyone votes
        # and it's approved. 
        key_action, result = christenClient.Resource.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=key_action.pk).status, "waiting")

        conditional_action = self.client.Conditional.get_condition_item_given_action_and_source(action_pk=key_action.pk,
            source_id="owner_"+str(self.community.pk))

        client = Client(target=conditional_action, actor=self.users.pinoe)
        client.VoteCondition.vote(vote="yea")
        client.VoteCondition.set_actor(actor=self.users.tobin)
        client.VoteCondition.vote(vote="yea")
        client.VoteCondition.set_actor(actor=self.users.jmac)
        client.VoteCondition.vote(vote="yea")
        client.VoteCondition.set_actor(actor=self.users.christen)
        client.VoteCondition.vote(vote="yea")

        # hack to get around the one hour minimum voting period
        conditional_action.voting_starts = timezone.now() - timedelta(hours=2)
        conditional_action.save(override_check=True)

        self.assertEquals(Action.objects.get(pk=key_action.pk).status, "implemented")
        resource = self.client.Resource.get_resource_given_pk(pk=self.resource.pk)
        self.assertTrue(resource[0].foundational_permission_enabled)

    def test_change_governors_requires_foundational_authority(self):

        # Pinoe is the owner, Sully and Pinoe are governors.
        self.client.Community.set_target(self.community)
        self.client.Community.add_members([self.users.sully.pk])
        action, result = self.client.Community.add_governor(governor_pk=self.users.sully.pk)
        self.assertEquals(self.community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})

        # Sully tries to add Aubrey as a governor.  She cannot, she is not an owner.
        self.client.Community.set_actor(actor=self.users.sully)
        action, result = self.client.Community.add_governor(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Rose tries to add Aubrey as a governor.  She cannot, she is not an owner.
        self.client.Community.set_actor(actor=self.users.rose)
        action, result = self.client.Community.add_governor(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Pinoe tries to add Aubrey as a governor.  She can, since has foundational authority.
        self.client.Community.set_actor(actor=self.users.pinoe)
        action, result = self.client.Community.add_governor(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.sully.pk, self.users.aubrey.pk], 
            'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_change_owners_requires_foundational_authority(self):

        # Pinoe adds Crystal as owner.  There are now two owners with no conditions.
        self.client.Community.set_target(self.community)
        self.client.Community.add_members([self.users.crystal.pk])
        action, result = self.client.Community.add_owner(owner_pk=self.users.crystal.pk)
        self.assertEquals(self.community.roles.get_owners(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Tobin tries to add Christen as owner.  She cannot, she is not an owner.
        self.client.Community.set_actor(actor=self.users.tobin)
        action, result = self.client.Community.add_owner(owner_pk=self.users.christen.pk)
        self.assertEquals(self.community.roles.get_owners(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Crystal tries to add Christen as owner.  She can, since has foundational authority.
        self.client.Community.set_actor(actor=self.users.crystal)
        action, result = self.client.Community.add_owner(owner_pk=self.users.christen.pk)
        self.assertEquals(self.community.roles.get_owners(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk, self.users.christen.pk], 
            'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_change_foundational_override_requires_foundational_authority(self):

        # Pinoe is the owner, Pinoe and Crystal are governors.
        self.client.Community.set_target(self.community)
        self.client.Community.add_members([self.users.crystal.pk])
        action, result = self.client.Community.add_governor(governor_pk=self.users.crystal.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.client.Resource.set_target(self.resource)

        # JJ tries to enable foundational override on resource. 
        # She cannot, she is not an owner.
        self.client.Resource.set_actor(actor=self.users.jj)
        action, result = self.client.Resource.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Crystal tries to enable foundational override on resource.
        # She cannot, she is not an owner.
        self.client.Resource.set_actor(actor=self.users.crystal)
        action, result = self.client.Resource.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Pinoe tries to enable foundational override on resource.
        # She can, since she is an owner and has foundational authority.
        self.client.Resource.set_actor(actor=self.users.pinoe)
        action, result = self.client.Resource.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertTrue(self.resource.foundational_permission_enabled)


class RolesetTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)
        self.community = self.client.Community.create_community(name="USWNT")
        self.client.Community.set_target(self.community)
        self.resource = self.client.Resource.create_resource(name="USWNT Resource")
        self.client.Resource.set_target(self.resource)
        self.client.Resource.change_owner_of_target(new_owner=self.community)

    # Test custom roles

    def test_basic_custom_role(self):

        # No custom roles so far
        roles = self.client.Community.get_custom_roles()
        self.assertEquals(roles, {})

        # Add a role
        action, result = self.client.Community.add_role(role_name="forwards")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_custom_roles()
        self.assertEquals(roles, {'forwards': []})

        # Add people to role
        self.client.Community.add_members([self.users.christen.pk, self.users.crystal.pk])
        action, result = self.client.Community.add_people_to_role(role_name="forwards", 
            people_to_add=[self.users.christen.pk, self.users.crystal.pk, self.users.pinoe.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["forwards"], 
            [self.users.christen.pk, self.users.crystal.pk, self.users.pinoe.pk])

        # Remove person from role
        action, result = self.client.Community.remove_people_from_role(role_name="forwards", 
            people_to_remove=[self.users.crystal.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["forwards"], [self.users.christen.pk, self.users.pinoe.pk])

        # Remove role
        action, result = self.client.Community.remove_role(role_name="forwards")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_custom_roles()
        self.assertEquals(roles, {})

    def test_basic_role_works_with_permission_item(self):

        # Aubrey wants to change the name of the resource, she can't
        self.client.Community.add_members([self.users.aubrey.pk])
        self.client.Resource.set_actor(actor=self.users.aubrey)
        action, result = self.client.Resource.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "USWNT Resource")

        # Pinoe adds a 'namers' role to the community which owns the resource
        self.client.Resource.set_actor(actor=self.users.pinoe)
        action, result = self.client.Community.add_role(role_name="namers")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.client.Community.refresh_target()
        roles = self.client.Community.get_custom_roles()
        self.assertEquals(roles, {'namers': []})

        # Pinoe creates a permission item with the 'namers' role in it
        self.client.PermissionResource.set_target(self.resource)
        action, result = self.client.PermissionResource.add_permission(permission_type=Changes().Resources.ChangeResourceName,
            permission_roles=["namers"])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Pinoe adds Aubrey to the 'namers' role in the community
        action, result = self.client.Community.add_people_to_role(role_name="namers", 
            people_to_add=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["namers"], [self.users.aubrey.pk])

        # Aubrey can now change the name of the resource
        self.client.Resource.set_actor(actor=self.users.aubrey)
        action, result = self.client.Resource.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

        # Pinoe removes Aubrey from the namers role in the community
        action, result = self.client.Community.remove_people_from_role(role_name="namers", 
            people_to_remove=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["namers"], [])

        # Aubrey can no longer change the name of the resource
        self.client.Resource.set_actor(actor=self.users.aubrey)
        action, result = self.client.Resource.change_name(new_name="A Newly Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_basic_role_works_with_governor(self):        

        # Pinoe adds the resource to her community
        self.client.Resource.set_target(target=self.resource)
        self.client.Resource.change_owner_of_target(new_owner=self.community)

        # Aubrey wants to change the name of the resource, she can't
        self.client.Resource.set_actor(actor=self.users.aubrey)
        action, result = self.client.Resource.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "USWNT Resource")

        # Pinoe adds member role to governors
        action, result = self.client.Community.add_governor_role(governor_role="members")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.client.Community.refresh_target()
        gov_info = self.client.Community.get_governorship_info()
        self.assertDictEqual(gov_info, {'actors': [self.users.pinoe.pk], 'roles': ['members']})

        # Aubrey tries to do a thing and can't
        action, result = self.client.Resource.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "USWNT Resource")

        # Pinoe adds Aubrey as a member
        action, result = self.client.Community.add_members(member_pk_list=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["members"], [self.users.pinoe.pk, self.users.aubrey.pk]) 

        # Aubrey tries to do a thing and can
        action, result = self.client.Resource.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_add_member_and_remove_member_from_roleset(self):

        self.assertEquals(self.client.Community.get_members(), [self.users.pinoe])

        # Pinoe adds Aubrey to the community
        self.client.Community.add_members([self.users.aubrey.pk])
        self.assertCountEqual(self.client.Community.get_members(), 
            [self.users.pinoe, self.users.aubrey])

        # Pinoe removes Aubrey from the community
        action, result = self.client.Community.remove_members([self.users.aubrey.pk])
        self.assertEquals(self.client.Community.get_members(), [self.users.pinoe])


class ResolutionFieldTest(DataTestCase):

    def setUp(self):

        # Create clients for Pinoe, create community
        self.client = Client(actor=self.users.pinoe)
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.Community.set_target(self.instance)
        self.client.Community.change_owner_of_target(new_owner=self.instance)  # Make community self-owned
        self.client.update_target_on_all(target=self.instance)  # make instance the default target for Pinoe

        # Make separate clients for Hao, Crystal, JJ
        self.haoClient = Client(actor=self.users.hao, target=self.instance)          # non-member
        self.roseClient = Client(actor=self.users.rose, target=self.instance)        # member
        self.jjClient = Client(actor=self.users.jj, target=self.instance)            # governing
        self.crystalClient = Client(actor=self.users.crystal, target=self.instance)  # roletest

        # Create request objects
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)
        self.haoRequest = Request(user=self.users.hao)
        self.roseRequest = Request(user=self.users.rose)
        self.jjRequest = Request(user=self.users.jj)
        self.crystalRequest = Request(user=self.users.crystal)

        # Pinoe adds members to community
        self.client.Community.add_members([self.users.jj.pk, self.users.crystal.pk, 
            self.users.rose.pk])

        # Pinoe adds a role to community and assign relevant members
        action, result = self.client.Community.add_role(role_name="midfielders")
        self.client.Community.add_people_to_role(role_name="midfielders", 
            people_to_add=[self.users.pinoe.pk, self.users.rose.pk])

    def test_resolution_field_correct_for_approved_action(self):

        # Add permission so any member can change the name of the group
        self.client.PermissionResource.add_permission(permission_roles=["members"],
            permission_type=Changes().Communities.ChangeName)

        # Rose, a member, changes the name
        action, result = self.roseClient.Community.change_name(new_name="Miscellaneous Badasses")
        self.assertEquals(action.status, "implemented")

        # Inspect action's resolution field
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "specific")
        self.assertFalse(action.resolution.conditions)

    def test_resolution_field_correct_for_rejected_action(self):

        # Add permission so any member can change the name of the group
        self.client.PermissionResource.add_permission(permission_roles=["members"],
            permission_type=Changes().Communities.ChangeName)

        # Non-member user changes name
        action, result = self.haoClient.Community.change_name(new_name="Miscellaneous Badasses")
        self.assertEquals(action.status, "rejected")

        # Inspect action's resolution field
        self.assertTrue(action.resolution.is_resolved)
        self.assertFalse(action.resolution.is_approved)
        self.assertFalse(action.resolution.conditions)

    def test_resolution_field_approved_through(self):
        
        # Pinoe can make JJ a governor because she has a foundational permission
        action, result = self.client.Community.add_governor(governor_pk=self.users.jj.pk)
        self.assertEquals(action.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "foundational")

        # JJ can change the name of the group because she has a governing permission.        
        action, result = self.jjClient.Community.change_name(new_name="Julie Ertz and Her Sidekicks")
        self.assertEquals(action.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "governing")

        # Crystal can change the name of the group because she has a specific permission.
        self.client.PermissionResource.add_permission(permission_actors=[self.users.crystal.pk],
            permission_type=Changes().Communities.ChangeName)
        action, result = self.crystalClient.Community.change_name(new_name="Crystal Dunn and Her Sidekicks")
        self.assertEquals(action.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "specific")

    def test_resolution_field_for_role_for_specific_permission(self):

        # Add permission so any member can change the name of the group
        self.client.PermissionResource.add_permission(permission_roles=["members"],
            permission_type=Changes().Communities.ChangeName)

        # When they change the name, the resolution role field shows the role
        action, result = self.roseClient.Community.change_name(new_name="Best Team")
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.specific_status, "approved")
        self.assertEquals(action.resolution.approved_through, "specific")
        self.assertEquals(action.resolution.approved_role, "members")

    def test_resolution_field_for_role_for_governing_permission(self):

        # Pinoe makes a governing role
        action, result = self.client.Community.add_governor_role(governor_role="midfielders")
        action, result = self.roseClient.Community.change_name(new_name="Best Team")
        self.assertEquals(action.resolution.approved_through, "governing")
        self.assertEquals(action.resolution.governing_status, "approved")
        self.assertEquals(action.resolution.approved_role, "midfielders")

    def test_resolution_field_for_individual_with_specific_permission(self):

        # Add permission so a specific person can change the name of the group
        self.client.PermissionResource.add_permission(permission_actors=[self.users.rose.pk],
            permission_type=Changes().Communities.ChangeName)

        # When they change the name, the resolution role field shows no role
        action, result = self.roseClient.Community.change_name(new_name="Best Team")
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "specific")
        self.assertFalse(action.resolution.approved_role)

    def test_resolution_field_captures_conditional_info(self):

        # Pinoe sets a permission on the community that any 'member' can change the name.
        action, permission = self.client.PermissionResource.add_permission(permission_roles=["members"],
            permission_type=Changes().Communities.ChangeName)

        # But then she adds a condition that someone needs to approve a name change 
        # before it can go through. 
        self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition")

        # (Since no specific permission is set on the condition, "approving" it 
        # requirest foundational or governing authority to change.  So only Pinoe 
        # can approve.)

        # HAO tries to change the name and fails because she is not a member.  The
        # condition never gets triggered.
        action, result = self.haoClient.Community.change_name(new_name="Let's go North Carolina!")
        self.assertEquals(action.status, "rejected")
        self.assertTrue(action.resolution.is_resolved)
        self.assertFalse(action.resolution.is_approved)
        self.assertFalse(action.resolution.conditions)

        # Rose tries to change the name and has to wait for approval.
        rose_action, result = self.roseClient.Community.change_name(new_name="Friends <3")
        self.assertEquals(rose_action.status, "waiting")
        self.assertEquals(rose_action.resolution.specific_status, "waiting")
        self.assertFalse(rose_action.resolution.is_resolved)
        self.assertFalse(rose_action.resolution.is_approved)
        self.assertTrue(rose_action.resolution.conditions)

        # Pinoe approves Rose's name change.
        condition_item = self.client.Conditional.get_condition_item_given_action_and_source(
            action_pk=rose_action.pk, source_id="perm_"+str(permission.pk))
        self.client.ApprovalCondition.set_target(target=condition_item)
        action, result = self.client.ApprovalCondition.approve()
        self.assertEquals(action.status, "implemented")

        # Rose's action is implemented
        rose_action.refresh_from_db()
        self.assertEquals(rose_action.status, "implemented")
        self.assertTrue(rose_action.resolution.is_resolved)
        self.assertTrue(rose_action.resolution.is_approved)
        self.assertEquals(rose_action.resolution.approved_condition, "approvalcondition")
        self.instance = self.client.Community.get_community(community_pk=str(self.instance.pk))
        self.assertEquals(self.instance.name, "Friends <3")

        # Rose tries to change the name again.  This time Pinoe rejects it, for Pinoe is fickle. 
        rose_action, result = self.roseClient.Community.change_name(new_name="BEST Friends <3")
        condition_item = self.client.Conditional.get_condition_item_given_action_and_source(
            action_pk=rose_action.pk, source_id="perm_"+str(permission.pk))
        self.client.ApprovalCondition.set_target(target=condition_item)
        action, result = self.client.ApprovalCondition.reject()
        rose_action.refresh_from_db()
        self.assertEquals(rose_action.status, "rejected")
        self.assertEquals(self.instance.name, "Friends <3")
        self.assertTrue(rose_action.resolution.is_resolved)
        self.assertFalse(rose_action.resolution.is_approved)

        
class ConfigurablePermissionTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community & client
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)

        # Add roles to community and assign members
        self.client.Community.add_members([self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.crystal.pk, self.users.jmac.pk,
            self.users.aubrey.pk, self.users.sonny.pk, self.users.sully.pk,
            self.users.jj.pk])
        self.client.Community.add_role(role_name="forwards")
        self.client.Community.add_role(role_name="spirit players")

        # Make separate clients for other users.
        self.tobinClient = Client(actor=self.users.tobin, target=self.instance)
        self.roseClient = Client(actor=self.users.rose, target=self.instance)
        self.sonnyClient = Client(actor=self.users.sonny, target=self.instance)

        # Create request objects
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)

    def test_configurable_permission(self):

        # Pinoe configures a position so that only Rose can add people to the Spirit Players role
        # and not the Forwards role
        self.client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddPeopleToRole,
            permission_actors=[self.users.rose.pk],
            permission_configuration={"role_name": "spirit players"})

        # Rose can add Aubrey to to the Spirit Players role
        action, result = self.roseClient.Community.add_people_to_role(role_name="spirit players", 
            people_to_add=[self.users.aubrey.pk])
        roles = self.client.Community.get_roles()
        self.assertEquals(roles["spirit players"], [self.users.aubrey.pk])
        
        # Rose cannot add Christen to the forwards role
        self.roseClient.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.christen.pk])
        roles = self.client.Community.get_roles()
        self.assertEquals(roles["forwards"], [])
  
    def test_configurable_metapermission(self):

        # Pinoe creates a role called 'admins' in community USWNT and adds Tobin to the role. She also
        # adds Rose to the 'spirit players' role.
        self.client.Community.add_role(role_name="admins")
        self.client.Community.add_people_to_role(role_name="admins", people_to_add=[self.users.tobin.pk])
        self.client.Community.add_people_to_role(role_name="spirit players", people_to_add=[self.users.rose.pk])

        # Pinoe creates a configured permission where people with role 'admins', as well as the role 
        # 'spirit players', can add people to the role 'forwards'.
        action, permission = self.client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddPeopleToRole,
            permission_roles=["admins", "spirit players"],
            permission_configuration={"role_name": "forwards"})
        self.assertCountEqual(permission.roles.role_list, ["admins", "spirit players"]) 

        # We test that Rose, in the role Spirit Players, can add JMac to forwards, and that 
        # Tobin, in the role admins, can add Christen to forwards.
        self.roseClient.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.jmac.pk])
        self.tobinClient.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.christen.pk])
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["forwards"], [self.users.jmac.pk, self.users.christen.pk])

        # Pinoe then creates a configured metapermission on that configured permission that allows
        # JJ to remove the role 'spirit players' but not admins.
        self.client.PermissionResource.set_target(permission)
        self.client.PermissionResource.add_permission(
            permission_type=Changes().Permissions.RemoveRoleFromPermission,
            permission_actors=[self.users.jj.pk],
            permission_configuration={"role_name": "spirit players"})

        # JJ tries to remove both.  She is successful in removing spirit players but not admins.
        self.jjClient = Client(actor=self.users.jj, target=permission)
        self.jjClient.PermissionResource.remove_role_from_permission(role_name="admins", permission_pk=permission.pk)
        self.jjClient.PermissionResource.remove_role_from_permission(role_name="spirit players", permission_pk=permission.pk)
        permission.refresh_from_db()
        self.assertCountEqual(permission.roles.role_list, ["admins"])        

        # We check again: Tobin, in the admin role, can add people to forwards, but 
        # Rose, in the spirit players, can no longer add anyone to forwards.
        self.tobinClient.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])
        self.roseClient.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.pinoe.pk])
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["forwards"], [self.users.jmac.pk, self.users.christen.pk, self.users.tobin.pk])


class MockActionTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a Community and Client and some members
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_members([self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.aubrey.pk])

    def test_single_mock_action(self):
        
        self.client.Community.mode = "mock"
        action = self.client.Community.add_role(role_name="forwards")
        self.assertTrue(action.is_mock)

    def test_check_permissions_for_action_group_when_user_has_unconditional_permission(self):

        from concord.actions.utils import check_permissions_for_action_group
        self.client.Community.mode = "mock"

        add_forwards_action = self.client.Community.add_role(role_name="forwards")
        add_mids_action = self.client.Community.add_role(role_name="midfielders")

        summary_status, log = check_permissions_for_action_group([add_forwards_action, add_mids_action])

        self.assertEquals(summary_status, "approved")
        self.assertEquals(log[0]["status"], "approved")
        self.assertEquals(log[0]["log"], "approved through governing with role None and condition None")
        self.assertEquals(log[1]["status"], "approved")
        self.assertEquals(log[1]["log"], "approved through governing with role None and condition None")

    def test_check_permissions_for_action_group_when_user_does_not_have_permission(self):

        # Pinoe sets specific permission that Tobin does not have
        action, permission = self.client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddRole,
            permission_actors=[self.users.christen.pk])

        from concord.actions.utils import check_permissions_for_action_group
        self.client.Community.mode = "mock"
        self.client.Community.set_actor(actor=self.users.tobin)

        add_forwards_action = self.client.Community.add_role(role_name="forwards")
        add_mids_action = self.client.Community.add_role(role_name="midfielders")

        summary_status, log = check_permissions_for_action_group([add_forwards_action, add_mids_action])

        self.assertEquals(summary_status, "rejected")
        self.assertEquals(log[0]["status"], "rejected")
        self.assertEquals(log[0]["log"], 'action did not meet any permission criteria')
        self.assertEquals(log[1]["status"], "rejected")
        self.assertEquals(log[1]["log"], 'action did not meet any permission criteria')

    def test_check_permissions_for_action_group_when_user_has_conditional_permission(self):

         # Pinoe sets specific permission & condition on that permission
        action, permission = self.client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddRole,
            permission_actors=[self.users.tobin.pk])
        perm_data = [ { "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.christen.pk] } ]
        self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition", 
            permission_data=perm_data)

        from concord.actions.utils import check_permissions_for_action_group
        self.client.Community.mode = "mock"
        self.client.Community.set_actor(actor=self.users.tobin)

        add_forwards_action = self.client.Community.add_role(role_name="forwards")
        add_mids_action = self.client.Community.add_role(role_name="midfielders")

        summary_status, log = check_permissions_for_action_group([add_forwards_action, add_mids_action])

        self.assertEquals(summary_status, "waiting")
        self.assertEquals(log[0]["status"], "waiting")
        self.assertTrue("waiting on condition(s) for governing and specific" in log[0]["log"])
        self.assertEquals(log[1]["status"], "waiting")
        self.assertTrue("waiting on condition(s) for governing and specific" in log[1]["log"])


class ActionContainerTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a Community and Clients
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)

        self.mock_action_list = []

        self.client.Community.mode = "mock"

        # Action 1: Add some members
        self.mock_action_list.append(self.client.Community.add_members([self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.aubrey.pk]))

        # Action 2: Add a role
        self.mock_action_list.append(self.client.Community.add_role(role_name="forwards"))

        # Action 3: Add another role
        self.mock_action_list.append(self.client.Community.add_role(role_name="spirit players"))

        # Action 4: Add people to first role
        self.mock_action_list.append(self.client.Community.add_people_to_role(role_name="forwards", 
            people_to_add=[self.users.christen.pk, self.users.tobin.pk]))

        # Action 5: Add people to second role
        self.mock_action_list.append(self.client.Community.add_people_to_role(role_name="spirit players", 
            people_to_add=[self.users.rose.pk, self.users.aubrey.pk]))

        self.client.Community.mode = "default"

        # create a fake trigger action
        action, result = self.client.Community.change_name(new_name="USWNT")
        self.mock_trigger_action = action

    def test_create_and_apply_container(self):

        actions = Action.objects.all()   # before container is created, only one aciton in DB (the fake trigger action)
        self.assertEquals(len(actions), 1)
        
        container, log = self.client.Action.create_action_container(action_list=self.mock_action_list,
            trigger_action=self.mock_trigger_action)

        actions = Action.objects.all()   # refresh
        self.assertEquals(len(actions), 6)
        self.assertEquals(container.status, "implemented")
        self.assertEquals(actions[1].container, container.pk)

        self.instance.refresh_from_db()
        self.assertCountEqual(self.instance.roles.get_custom_roles(), {'forwards': [self.users.christen.pk, self.users.tobin.pk], 
            'spirit players': [self.users.rose.pk, self.users.aubrey.pk]})

    def test_container_rejects_when_an_action_is_rejected(self):
        
        # remove pinoe as governor so she no longer has permission to take the mock actions
        action, result = self.client.Community.remove_governor(governor_pk=self.users.pinoe.pk)

        # container is rejected
        container, log = self.client.Action.create_action_container(action_list=self.mock_action_list,
            trigger_action=self.mock_trigger_action)
        self.assertEquals(container.status, "rejected")

        # changes are not made
        self.assertEquals(self.instance.roles.get_custom_roles(), {})

    def test_container_creates_conditions_for_actions(self):

        # swap governors so Pinoe doesn't just automatically pass everything
        self.client.Community.add_members([self.users.crystal.pk])
        self.client.Community.add_governor(governor_pk=self.users.crystal.pk)
        action, result = self.client.Community.remove_governor(governor_pk=self.users.pinoe.pk)
        self.client.PermissionResource.set_actor(actor=self.users.crystal)

        # new governor, Crystal, adds specific permissions for Pinoe to take the five actions
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Communities.AddMembers,
            permission_actors=[self.users.pinoe.pk])
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Communities.AddRole,
            permission_actors=[self.users.pinoe.pk])
        action, permission = self.client.PermissionResource.add_permission(permission_type=Changes().Communities.AddPeopleToRole,
            permission_actors=[self.users.pinoe.pk])
        # add condition to one of the permissions
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.pinoe.pk] }]
        action, result = self.client.PermissionResource.add_condition_to_permission(permission_pk=permission.pk, 
            condition_type="approvalcondition", condition_data={"self_approval_allowed": True}, 
            permission_data=permission_data)
        
        # now apply container/template containing Pinoe's actions
        container, log = self.client.Action.create_action_container(action_list=self.mock_action_list,
            trigger_action=self.mock_trigger_action)
        self.assertEquals(container.status, "waiting")

        # crystal gets conditions from container and approves them
        crystalClient = Client(actor=self.users.crystal)
        for condition in container.context.get_conditions():
            crystalClient.ApprovalCondition.set_target(target=condition)
            crystalClient.ApprovalCondition.approve()

        # retry Pinoe's actions
        container, log = self.client.Action.retry_action_container(container_pk=container.pk)
        self.assertEquals(container.status, "implemented")
        self.instance.refresh_from_db()
        self.assertCountEqual(self.instance.roles.get_custom_roles(), {'forwards': [self.users.christen.pk, self.users.tobin.pk], 
            'spirit players': [self.users.rose.pk, self.users.aubrey.pk]})        


class TemplateTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a Community and Client
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_role(role_name="forwards")
        self.client.Community.add_members([self.users.tobin.pk])
        self.client.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

    def test_create_invite_only_template_creates_template(self):
        template_model = template_library.create_invite_only_template()
        self.assertEquals(template_model.name, "Invite Only")

    def test_apply_invite_only_template_to_community(self):
        
        # Before applying template, Tobin (with role Forward) cannot add members
        self.client.Community.set_actor(actor=self.users.tobin)
        action, result = self.client.Community.add_members([self.users.christen.pk])
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.client.Community.get_members(), [self.users.pinoe, self.users.tobin])

        # Pinoe applies template model to community
        supplied_fields = { "addmembers_permission_roles": ["forwards"], 
            "addmembers_permission_actors": [] }
        template_model = template_library.create_invite_only_template()
        action, container = self.client.Template.apply_template(template_model_pk=template_model.pk,
            supplied_fields=supplied_fields)
        self.assertEquals(container.status, "implemented")

        # now Tobin can add members
        action, result = self.client.Community.add_members([self.users.christen.pk])
        self.assertEquals(action.status, "implemented")
        

class PermissionedReadTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community with roles
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_role(role_name="forwards")
        self.client.Community.add_members([self.users.tobin.pk, self.users.rose.pk])
        self.client.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

        # Create a resource and put it in the community
        self.resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.Resource.set_target(target=self.resource)
        self.client.Resource.change_owner_of_target(new_owner=self.instance)

        # create clients for users
        self.tobinClient = Client(actor=self.users.tobin, target=self.resource)
        self.roseClient = Client(actor=self.users.rose, target=self.resource)

    def test_unconfigured_permission_read(self):
        # Only people with role "forwards" can view the resource
        action, result = self.client.PermissionResource.add_permission(permission_type=Changes().Actions.View, 
            permission_roles=["forwards"])

        # User Rose without role 'forwards' can't see object
        action, result = self.roseClient.Resource.get_target_data()
        self.assertEquals(action.status, "rejected")

        # User Tobin with role 'forwards' can see object
        action, result = self.tobinClient.Resource.get_target_data()
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, 
            { 'id': 1,
            "item": [],
            'foundational_permission_enabled': False, 
            'governing_permission_enabled': True, 
            'name': 'Go USWNT!', 
            'owner': "USWNT"})

    def test_can_configure_readable_fields(self):
        # Only people with role "forwards" can view the resource field "name" and resource "id"
        action, result = self.client.PermissionResource.add_permission(permission_type=Changes().Actions.View, 
            permission_roles=["forwards"], permission_configuration={"fields_to_include": ["name", "id"]})

        # They try to get other fields, get error
        action, result = self.tobinClient.Community.get_target_data(fields_to_include=["owner"])
        self.assertEquals(action.status, "rejected")
        self.assertTrue("Cannot view fields owner" in action.resolution.log)
        
        # They try to get the right field, success
        action, result = self.tobinClient.Community.get_target_data(fields_to_include=["name"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!'})

        # They try to get two fields at once, success
        action, result = self.tobinClient.Community.get_target_data(fields_to_include=["name", "id"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!', "id": 1})

        # They try to get one allowed field and one unallowed field, error
        action, result = self.tobinClient.Community.get_target_data(fields_to_include=["name", "owner"])
        self.assertEquals(action.status, "rejected")
        self.assertTrue("Cannot view fields owner" in action.resolution.log)

        # They try to get a nonexistent field, error
        result = self.tobinClient.Community.get_target_data(fields_to_include=["potato"])
        self.assertTrue(result, "Attempting to view field(s) potato that are not on target Resource object (1)")

    def test_multiple_readpermissions(self):

        # Permission 1: user Tobin can only see field "name"
        action, result = self.client.PermissionResource.add_permission(permission_type=Changes().Actions.View, 
            permission_actors=[self.users.tobin.pk], 
            permission_configuration={"fields_to_include": ["name"]})

        # Permission 2: user Rose can only see field "owner"
        action, result = self.client.PermissionResource.add_permission(permission_type=Changes().Actions.View, 
            permission_actors=[self.users.rose.pk], 
            permission_configuration={"fields_to_include": ["owner"]})

        # Tobin can see name but not owner
        action, result = self.tobinClient.Resource.get_target_data(fields_to_include=["name"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!'})
        action, result = self.tobinClient.Resource.get_target_data(fields_to_include=["owner"])
        self.assertEquals(action.status, "rejected")
        self.assertTrue("Cannot view fields owner" in action.resolution.log)

        # Rose can see owner but not name
        action, result = self.roseClient.Resource.get_target_data(fields_to_include=["owner"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'owner': 'USWNT'})
        action, result = self.roseClient.Resource.get_target_data(fields_to_include=["name"])
        self.assertEquals(action.status, "rejected")
        self.assertTrue("Cannot view fields name" in action.resolution.log)


class CommentTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community with roles
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.Community.set_target(self.instance)
        self.client.Community.add_role(role_name="forwards")
        self.client.Community.add_members([self.users.tobin.pk, self.users.rose.pk])
        self.client.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

        # Create a resource and put it in the community
        self.resource = self.client.Resource.create_resource(name="Go USWNT!")
        self.client.Resource.set_target(target=self.resource)
        self.client.Resource.change_owner_of_target(new_owner=self.instance)

        # Create target of comment client
        self.client.Comment.set_target(self.resource)

    def test_add_comment(self):

        # we start off with no comments
        comments = list(self.client.Comment.get_all_comments_on_target())
        self.assertEquals(comments, [])

        # we add a comment and now we have one on the target
        self.client.Comment.add_comment(text="This is a new comment")
        comments = self.client.Comment.get_all_comments_on_target()
        self.assertEquals(comments.first().text, "This is a new comment")

    def test_edit_comment(self):

        # we start off by adding a comment
        self.client.Comment.add_comment(text="This is a new comment")
        comments = self.client.Comment.get_all_comments_on_target()
        self.assertEquals(comments.first().text, "This is a new comment")

        # when we edit it, the text changes
        self.client.Comment.edit_comment(pk=comments.first().pk, text="This is an edited comment")
        comments = self.client.Comment.get_all_comments_on_target()  # refresh
        self.assertEquals(comments.first().text, "This is an edited comment")

    def test_delete_comment(self):

        # we start off by adding a comment
        self.client.Comment.add_comment(text="This is a new comment")
        comments = self.client.Comment.get_all_comments_on_target()
        self.assertEquals(comments.first().text, "This is a new comment")

        # when we delete it, it disappears
        self.client.Comment.delete_comment(pk=comments.first().pk)
        comments = self.client.Comment.get_all_comments_on_target()  # refresh
        self.assertEquals(list(comments), [])


