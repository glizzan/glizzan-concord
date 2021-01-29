"""Resource State Changes"""

import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from concord.resources.models import Resource, Item, Comment, SimpleList
from concord.actions.state_changes import BaseStateChange
from concord.utils.lookups import get_all_permissioned_models
from concord.utils import field_utils


logger = logging.getLogger(__name__)


#############################
### Comment State Changes ###
#############################


class AddCommentStateChange(BaseStateChange):
    """State Change to add a comment."""

    change_description = "Add comment"
    section = "Comment"
    model_based_validation = (Comment, ["text"])
    context_keys = ["commented_object"]
    configurable_fields = ["original_creator_only", "target_type"]

    # Fields
    text = field_utils.CharField(label="Comment text", required=True)
    original_creator_only = field_utils.BooleanField(label="Only the creator of this comment's target can add comment")
    target_type = field_utils.CharField(label="Add comments only to this type of target")

    def __init__(self, text, original_creator_only=False, target_type=None):
        super().__init__()
        self.text = text
        self.original_creator_only = original_creator_only
        self.target_type = target_type

    def description_present_tense(self):
        return "add comment"

    def description_past_tense(self):
        return "added comment"

    @classmethod
    def get_context_instances(cls, action):
        """Returns the commented object by its model name, to handle cases where the referer knows the model type
        vs doesn't know the model type."""
        commented_object = action.target
        model_name = commented_object.__class__.__name__.lower()
        return {"commented_object": commented_object, model_name: commented_object}

    @classmethod
    def get_configured_field_text(cls, conf):
        target_type = conf["target_type"] if "target_type" in conf and conf["target_type"] else None
        creator_only = conf["original_creator_only"] if "original_creator_only" in conf and  \
            conf['original_creator_only'] else None

        if target_type and creator_only:
            return f", but only if the target is of type {conf['target_type']} and the user is " + \
                   "the creator of the object commented on"

        if target_type:
            return f", but only if the target is of type {conf['target_type']}"

        if creator_only:
            return ", but only if the user is the creator of the object commented on"

        return ""

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        original_creator_only = "original_creator_only" in configuration and configuration['original_creator_only']
        if original_creator_only:
            if configuration["original_creator_only"] not in [True, False, "True", "False", "true", "false"]:
                e = f"original_creator_only must be set to True or False, not {configuration['original_creator_only']}"
                return False, e
        if "target_type" in configuration and configuration["target_type"]:
            allowable_types = [mclass.__name__.lower() for mclass in get_all_permissioned_models()] + ["action"]
            if configuration["target_type"] not in allowable_types:
                return False, f'target_type must be a permissioned model or action, not {configuration["target_type"]}'
        return True, ""

    def check_configuration(self, action, permission):
        configuration = permission.get_configuration()
        original_creator_only = "original_creator_only" in configuration and configuration['original_creator_only']
        if original_creator_only:
            error_message = "original_creator_only is true, so the actor must have created the target of the comment"
            if hasattr(action.target, "author"):
                if action.actor.pk != action.target.author:
                    return False, error_message
            if hasattr(action.target, "creator"):
                if action.actor.pk != action.target.creator:
                    return False, error_message
        if "target_type" in configuration and configuration["target_type"]:
            target_type = configuration["target_type"]
            target_class = action.target.__class__.__name__.lower()
            if target_class != target_type and not (target_class == "commentcatcher" and target_type == "action"):
                return False, f'target type {configuration["target_type"]} does not match {target_class}'
        return True, None

    def implement(self, actor, target, **kwargs):

        comment = Comment(text=self.text, commentor=actor)
        comment.commented_object = target
        comment.owner = target.get_owner()
        comment.save()

        self.set_default_permissions(actor, comment)

        return comment


class EditCommentStateChange(BaseStateChange):
    """State Change to edit a comment."""
    change_description = "Edit comment"
    section = "Comment"
    context_keys = ["comment", "commented_object"]
    model_based_validation = (Comment, ["text"])
    configurable_fields = ["original_creator_only", "commenter_only"]
    allowable_targets = [Comment]
    settable_classes = ["all_models"]

    # Fields
    text = field_utils.CharField(label="Comment text", required=True)
    commenter_only = field_utils.BooleanField(label="Only the commenter can edit the comment")
    original_creator_only = field_utils.BooleanField(label="Only the creator of this comment's target can add comment")

    def __init__(self, text, commenter_only=False, original_creator_only=False):
        super().__init__()
        self.text = text
        self.commenter_only = commenter_only
        self.original_creator_only = original_creator_only

    @classmethod
    def return_configured_settings(self, configuration):
        commenter_only = "commenter_only" in configuration and configuration['commenter_only']
        original_creator_only = "original_creator_only" in configuration and configuration['original_creator_only']
        return commenter_only, original_creator_only

    @classmethod
    def get_configured_field_text(cls, configuration):
        commenter_only, original_creator_only = cls.return_configured_settings(configuration)
        if commenter_only:
            return ", but only if the user is the commenter"
        if original_creator_only:
            return ", but only if the user is the creator of the thing being commented on"
        return ""

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        commenter_only, original_creator_only = cls.return_configured_settings(configuration)
        if commenter_only:
            if configuration["commenter_only"] not in [True, False, "True", "False", "true", "false"]:
                return False, f"commenter_only must be set to True or False, not {configuration['commenter_only']}"
        if original_creator_only:
            if configuration["original_creator_only"] not in [True, False, "True", "False", "true", "false"]:
                e = f"original_creator_only must be set to True or False, not {configuration['original_creator_only']}"
                return False, e
        return True, ""

    def check_configuration(self, action, permission):
        commenter_only, original_creator_only = self.return_configured_settings(permission.get_configuration())
        if commenter_only:
            if action.actor.pk != action.target.commenter.pk:
                return False, "commenter_only is set to true, so the actor must the person who made the comment"
        if original_creator_only:
            error_message = "original_creator_only is true, so the actor must have created the target of the comment"
            if hasattr(action.target.commented_object, "author"):
                if action.actor.pk != action.target.commented_object.author:
                    return False, error_message
            if hasattr(action.target.commented_object, "creator"):
                if action.actor.pk != action.target.commented_object.creator:
                    return False, error_message
        return True, None

    @classmethod
    def get_context_instances(cls, action):
        """Returns the comment and the commented object. Also returns the commented object by its model
        name, to handle cases where the referer knows the model type vs doesn't know the model type."""
        comment = action.target
        commented_object = action.target.commented_object
        model_name = commented_object.__class__.__name__.lower()
        return {"comment": comment, "commented_object": commented_object, model_name: commented_object}

    def description_present_tense(self):
        return "edit comment"

    def description_past_tense(self):
        return "edited comment"

    def implement(self, actor, target, **kwargs):
        target.text = self.text
        target.save()
        return target


class DeleteCommentStateChange(BaseStateChange):
    """State Change to delete a comment."""
    change_description = "Delete comment"
    section = "Comment"
    context_keys = ["comment", "commented_object"]
    configurable_fields = ["original_creator_only", "commenter_only"]
    allowable_targets = [Comment]
    settable_classes = ["all_models"]

    # Fields
    commenter_only = field_utils.BooleanField(label="Only the commenter can delete the comment")
    original_creator_only = field_utils.BooleanField(label="Only the creator of this comment's target can delete comment")

    def __init__(self, commenter_only=False, original_creator_only=False):
        super().__init__()
        self.commenter_only = commenter_only
        self.original_creator_only = original_creator_only

    @classmethod
    def return_configured_settings(self, configuration):
        commenter_only = "commenter_only" in configuration and configuration['commenter_only']
        original_creator_only = "original_creator_only" in configuration and configuration['original_creator_only']
        return commenter_only, original_creator_only

    @classmethod
    def get_configured_field_text(cls, configuration):
        commenter_only, original_creator_only = cls.return_configured_settings(configuration)
        if commenter_only:
            return ", but only if the user is the commenter"
        if original_creator_only:
            return ", but only if the user is the creator of the thing being commented on"
        return ""

    @classmethod
    def check_configuration_is_valid(cls, configuration):
        """Used primarily when setting permissions, this method checks that the supplied configuration is a valid one.
        By contrast, check_configuration checks a specific action against an already-validated configuration."""
        commenter_only, original_creator_only = cls.return_configured_settings(configuration)
        if commenter_only:
            if configuration["commenter_only"] not in [True, False, "True", "False", "true", "false"]:
                return False, f"commenter_only must be set to True or False, not {configuration['commenter_only']}"
        if original_creator_only:
            if configuration["original_creator_only"] not in [True, False, "True", "False", "true", "false"]:
                e = f"original_creator_only must be set to True or False, not {configuration['original_creator_only']}"
                return False, e
        return True, ""

    def check_configuration(self, action, permission):
        commenter_only, original_creator_only = self.return_configured_settings(permission.get_configuration())
        if commenter_only:
            if action.actor.pk != action.target.commenter.pk:
                return False, "commenter_only is set to true, so the actor must the person who made the comment"
        if original_creator_only:
            error_message = "original_creator_only is true, so the actor must have created the target of the comment"
            if hasattr(action.target.commented_object, "author"):
                if action.actor.pk != action.target.commented_object.author:
                    return False, error_message
            if hasattr(action.target.commented_object, "creator"):
                if action.actor.pk != action.target.commented_object.creator:
                    return False, error_message
        return True, None

    @classmethod
    def get_context_instances(cls, action):
        """Returns the comment and the commented object. Also returns the commented object by its model
        name, to handle cases where the referer knows the model type vs doesn't know the model type."""
        comment = action.target
        commented_object = action.target.commented_object
        model_name = commented_object.__class__.__name__.lower()
        return {"comment": comment, "commented_object": commented_object, model_name: commented_object}

    def description_present_tense(self):
        return "delete comment"

    def description_past_tense(self):
        return "deleted comment"

    def implement(self, actor, target, **kwargs):
        from concord.permission_resources.utils import delete_permissions_on_target
        pk = target.pk
        delete_permissions_on_target(target)
        target.delete()
        return pk


#####################################
### Resource & Item State Changes ###
#####################################


class ChangeResourceNameStateChange(BaseStateChange):
    """State Change to change a resource name."""
    change_description = "Change name of resource"
    preposition = "for"
    model_based_validation = ("target", ["name"])
    allowable_targets = [Resource, Item]
    settable_classes = ["all_models"]

    # Fields
    name = field_utils.CharField(label="New name", required=True)

    def __init__(self, name):
        super().__init__()
        self.name = name

    def description_present_tense(self):
        return f"change name of resource to {self.name}"

    def description_past_tense(self):
        return f"changed name of resource to {self.name}"

    def implement(self, actor, target, **kwargs):
        target.name = self.name
        target.save()
        return target


class AddItemStateChange(BaseStateChange):
    """State Change to add item to a resource."""
    change_description = "Add item to resource"
    model_based_validation = (Item, ["name"])
    allowable_targets = [Resource]
    settable_classes = ["all_community_models", Resource]

    # Fields
    name = field_utils.CharField(label="New name", required=True)

    def __init__(self, name):
        super().__init__()
        self.name = name

    def description_present_tense(self):
        return f"add item {self.name}"

    def description_past_tense(self):
        return f"added item {self.name}"

    def implement(self, actor, target, **kwargs):
        item = Item.objects.create(name=self.name, resource=target, owner=actor.default_community)
        self.set_default_permissions(actor, item)
        return item


class RemoveItemStateChange(BaseStateChange):
    """State Change to remove item from a resource."""
    change_description = "Remove item from resource"
    preposition = "from"
    allowable_targets = [Item]
    settable_classes = ["all_community_models", Resource, Item]

    def description_present_tense(self):
        return "remove item"

    def description_past_tense(self):
        return "removed item"

    def implement(self, actor, target, **kwargs):
        try:
            from concord.permission_resources.utils import delete_permissions_on_target
            delete_permissions_on_target(target)
            target.delete()
            return True
        except ObjectDoesNotExist as exception:
            logger.warning(exception)
            return False


################################
### SimpleList State Changes ###
################################


class AddListStateChange(BaseStateChange):
    """State Change to create a list in a community (or other target)."""
    change_description = "Add list"
    section = "List"
    model_based_validation = (SimpleList, ["name", "description"])
    allowable_targets = ["all_community_models"]

    # Fields
    name = field_utils.CharField(label="Name", required=True)
    configuration = field_utils.DictField(label="Configuration", required=True)
    description = field_utils.CharField(label="Description")

    def __init__(self, name, configuration, description=None):
        super().__init__()
        self.name = name
        self.configuration = configuration
        self.description = description if description else ""

    def description_present_tense(self):
        return f"add list with name {self.name}"

    def description_past_tense(self):
        return f"added list with name {self.name}"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        try:
            SimpleList().validate_configuration(self.configuration)
            return True
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False

    def implement(self, actor, target, **kwargs):
        simple_list = SimpleList(name=self.name, description=self.description, owner=target.get_owner(), creator=actor)
        simple_list.set_row_configuration(self.configuration)
        simple_list.save()
        self.set_default_permissions(actor, simple_list)
        return simple_list


class EditListStateChange(BaseStateChange):
    """State Change to edit an existing list."""
    change_description = "Edit list"
    section = "List"
    model_based_validation = ("target", ["name", "description"])
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    # Fields
    name = field_utils.CharField(label="Name")
    configuration = field_utils.DictField(label="Configuration")
    description = field_utils.CharField(label="Description")

    def __init__(self, name=None, configuration=None, description=None):
        super().__init__()
        self.name = name
        self.configuration = configuration
        self.description = description

    def description_present_tense(self):
        return f"edit list with new name {self.name} and new description {self.description}"

    def description_past_tense(self):
        return f"edited list with new name {self.name} and new description {self.description}"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        if not self.name and not self.description and not self.configuration:
            self.set_validation_error(message="Must supply new name, description, or configuration when editing List.")
            return False
        if self.configuration:
            try:
                target.validate_configuration(self.configuration)
                target.adjust_rows_to_new_configuration(self.configuration)
                return True
            except ValidationError as error:
                self.set_validation_error(message=error.message)
                return False
        return True

    def implement(self, actor, target, **kwargs):
        target.name = self.name if self.name else target.name
        target.description = self.description if self.description else target.description
        if self.configuration:
            target.set_row_configuration(self.configuration)
        target.save()
        return target


class DeleteListStateChange(BaseStateChange):
    """State Change to delete an existing list."""
    change_description = "Delete list"
    section = "List"
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    def description_present_tense(self):
        return "delete list"

    def description_past_tense(self):
        return "deleted list"

    def implement(self, actor, target, **kwargs):
        pk = target.pk
        target.delete()
        return pk


class AddRowStateChange(BaseStateChange):
    """State Change to add a row to a list."""
    change_description = "Add row to list"
    section = "List"
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    # Fields
    row_content = field_utils.CharField(label="Content of row", required=True)
    index = field_utils.IntegerField(label="Index of row")

    def __init__(self, row_content, index=None):
        super().__init__()
        self.row_content = row_content
        self.index = index

    def description_present_tense(self):
        return f"add row with content {self.row_content}"

    def description_past_tense(self):
        return f"added row with content {self.row_content}"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        try:
            target.check_row_against_configuration(self.row_content)
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False
        if self.index and not isinstance(self.index, int):
            self.set_validation_error(message="Index must be an integer.")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.add_row(self.row_content, self.index)
        target.save()
        return target


class EditRowStateChange(BaseStateChange):
    """State Change to edit a row in a list."""
    change_description = "Edit row in list"
    section = "List"
    row_content = field_utils.CharField(label="Content of row", required=True)
    index = field_utils.IntegerField(label="Index of row", required=True)
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    def __init__(self, row_content, index):
        super().__init__()
        self.row_content = row_content
        self.index = index

    def description_present_tense(self):
        return f"edit row with index {self.index} to have new content {self.row_content}"

    def description_past_tense(self):
        return f"edited row with index {self.index} to have new content {self.row_content}"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        try:
            target.check_row_against_configuration(self.row_content)
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False
        if not isinstance(self.index, int):
            self.set_validation_error(message="Index must be an integer.")
            return False
        if not 0 <= self.index < len(target.get_rows()):
            self.set_validation_error(message=f"Index must be within 0 and {len(target.get_rows())} not {self.index}")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.edit_row(self.row_content, self.index)
        target.save()
        return target


class MoveRowStateChange(BaseStateChange):
    """State Change to move a row in a list."""
    change_description = "Move row in list"
    section = "List"
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    # Fields

    old_index = field_utils.IntegerField(label="Old index of row", required=True)
    new_index = field_utils.IntegerField(label="New index of row", required=True)

    def __init__(self, old_index, new_index):
        super().__init__()
        self.old_index = old_index
        self.new_index = new_index

    def description_present_tense(self):
        return f"move row with current index {self.old_index} to {self.new_index}"

    def description_past_tense(self):
        return f"moved row with current index {self.old_index} to {self.new_index}"

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target):
            return False

        if not isinstance(self.old_index, int):
            self.set_validation_error(message="Current index must be an integer.")
            return False

        if not isinstance(self.new_index, int):
            self.set_validation_error(message="New index must be an integer.")
            return False

        if not 0 <= self.old_index < len(target.get_rows()):
            message = f"Current index must be within 0 and {len(target.get_rows())} not {self.old_index}"
            self.set_validation_error(message=message)
            return False

        if not 0 <= self.new_index < len(target.get_rows()):
            message = f"New index must be within 0 and {len(target.get_rows())} not {self.new_index}"
            self.set_validation_error(message=message)
            return False

        return True

    def implement(self, actor, target, **kwargs):
        target.move_row(self.old_index, self.new_index)
        target.save()
        return target


class DeleteRowStateChange(BaseStateChange):
    """State Change to delete a row in a list."""
    change_description = "Delete row in list"
    section = "List"
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    # Fields
    index = field_utils.IntegerField(label="Index of row to delete", required=True)

    def __init__(self, index):
        super().__init__()
        self.index = index

    def description_present_tense(self):
        return f"delete row with index {self.index}"

    def description_past_tense(self):
        return f"deleted row with index {self.index}"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        if not isinstance(self.index, int):
            self.set_validation_error(message="Index must be an integer.")
            return False
        if not 0 <= self.index < len(target.get_rows()):
            self.set_validation_error(message=f"Index must be within 0 and {len(target.get_rows())} not {self.index}")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.delete_row(int(self.index))
        target.save()
        return target
