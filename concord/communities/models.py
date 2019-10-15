import json

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save

from concord.actions.models import PermissionedModel
from concord.conditionals.client import CommunityConditionalClient
from concord.communities.customfields import RoleHandler, RoleField


# TODO: put this somewhere more sensible (or maybe all this stringy stuff should go in templatetags)
def english_list(list_to_display):
    if len(list_to_display) <= 1:
        return "".join(list_to_display)
    return ", ".join(list_to_display[:-1]) + " and " + "".join(list_to_display[-1])


################################
### Community Resource/Items ###
################################

class BaseCommunityModel(PermissionedModel):
    '''The base community model is the abstract type for all communities.  Much of its 
    logic is contained in customfields.RoleField and customfields.RoleHandler.'''
    is_community = True

    name = models.CharField(max_length=200)    
    roles = RoleField(default=RoleHandler)

    class Meta:
        abstract = True

    def get_name(self):
        return self.name

    def get_owner(self):
        """
        Communities own themselves by default, although subtypes may differ.
        """
        return self
    
    def owner_list_display(self):
        """
        Helper function to display results of list_owners() more nicely.
        """
        owners = self.list_owners()
        has_actors = 'actors' in owners and owners['actors']
        has_roles = 'roles' in owners and owners['roles']
        if has_actors and has_roles:
            return english_list(owners['actors']) + " and people in roles " + english_list(owners['roles'])
        if has_actors:
            return english_list(owners['actors'])
        if has_roles:
            return "people in roles " + english_list(owners['roles'])

    def governor_list_display(self):
        """
        Helper function to display results of list_governors() more nicely.
        """
        governors = self.list_governors()
        has_actors = 'actors' in governors and governors['actors']
        has_roles = 'roles' in governors and governors['roles']
        if has_actors and has_roles:
            return english_list(governors['actors']) + " and people in roles " + english_list(governors['roles'])
        if has_actors:
            return english_list(governors['actors'])
        if has_roles:
            return "people in roles " + english_list(governors['roles'])

    def owner_condition_display(self):
        comCondClient = CommunityConditionalClient(system=True, target=self)
        owner_condition = comCondClient.get_condition_info_for_owner()
        return owner_condition if owner_condition else "unconditional"

    def governor_condition_display(self):
        comCondClient = CommunityConditionalClient(system=True, target=self)
        governor_condition = comCondClient.get_condition_template_for_governor()
        return governor_condition if governor_condition else "unconditional"

    # BUG: maybe overwrite save method to raise error if there community's rolefield
    # doesn't meet bare minimum valid conditions?


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
