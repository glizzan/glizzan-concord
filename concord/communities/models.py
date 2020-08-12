import json

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.contrib.contenttypes.fields import GenericRelation


from concord.actions.models import PermissionedModel
from concord.communities.customfields import RoleHandler, RoleField
from concord.actions.customfields import TemplateField, Template


################################
### Community Resource/Items ###
################################

class BaseCommunityModel(PermissionedModel):
    '''The base community model is the abstract type for all communities.  Much of its 
    logic is contained in customfields.RoleField and customfields.RoleHandler.'''
    is_community = True

    name = models.CharField(max_length=200)    
    roles = RoleField(default=RoleHandler)

    owner_condition = TemplateField(default=Template, system=True)
    governor_condition = TemplateField(default=Template, system=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"CommunityModel(pk={self.pk}, name={self.name}, roles={self.roles}, " + \
               f"owner_condition={self.has_condition('owner')}, governor_condition={self.has_condition('governor')}"

    def get_name(self):
        return self.__str__()

    def get_owner(self):
        """
        Communities own themselves by default, although subtypes may differ.
        """
        return self

    def has_condition(self, leadership_type):
        if leadership_type == "owner":
            return self.has_owner_condition()
        elif leadership_type == "governor":
            return self.has_governor_condition()

    def get_condition(self, leadership_type):
        if leadership_type == "owner":
            return self.owner_condition
        elif leadership_type == "governor":
            return self.governor_condition

    def has_owner_condition(self):
        if self.owner_condition and self.owner_condition.has_template():
            return True
        return False

    def has_governor_condition(self):
        if self.governor_condition and self.governor_condition.has_template():
            return True
        return False

    def get_condition_data(self, leadership_type, info="all"):
        """Uses the change data saved in the mock actions to instantiate the condition and permissions
        that will be created and get their info, to be used in forms"""
        from concord.conditionals.utils import generate_condition_form_from_action_list

        if leadership_type == "owner" and self.has_owner_condition():
            action_list = self.owner_condition.action_list
        elif leadership_type == "governor" and self.has_governor_condition():
            action_list = self.governor_condition.action_list
        else:
            return

        return generate_condition_form_from_action_list(action_list, info)


class Community(BaseCommunityModel):
    """
    A community is, at heart, a collection of users.  Communities 
    govern resources that determine how these users interact, either
    moderating discussion spaces, like a community forum, setting
    restrictions on membership lists, or by setting access rules for
    resources owned by the community, such as saying only admins
    may edit data added to a dataset.
    """
    ...

class DefaultCommunity(BaseCommunityModel):
    """
    Every user has a default community of which they are the BDFL.  (They can
    theoretically give someone else power over their default community, but we should 
    probably prevent that on the backend.)

    We're almost always accessing this through the related_name.  We have the user, and
    we want to know what community to stick our object in.
    """
    user_owner = models.OneToOneField(User, on_delete=models.CASCADE, 
        related_name="default_community")
 

def create_default_community(sender, instance, created, **kwargs):
    if created:
        name = "%s's Default Community" % instance.username
        roles = RoleHandler()
        roles.initialize_with_creator(creator=instance.pk)
        community = DefaultCommunity.objects.create(name=name, user_owner=instance,
            roles=roles)

post_save.connect(create_default_community, sender=User)
