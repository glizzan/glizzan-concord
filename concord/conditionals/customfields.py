import json, importlib, inspect

from django.db import models
from django.core.exceptions import ValidationError



#####################
### Custom Object ###
#####################


class ConditionData(object):
    '''
    Every condition template contains data about the conditions that will be instantiated, its "configuration."
    This object allows us to do precise validation, so we don't end up with data formatting errors.
    '''
    condition_type = None   
    condition_data = None
    condition_object = None 
    permission_data = None
    action_sourced_fields = None
    target_type = None

    # init & validation methods

    def __init__(self, *, condition_type=None, condition_data=None, permission_data=None, action_sourced_fields=None,
        target_type=None, validate=True):
        """Initializes the object using subset of data. When validate=false, doesn't check that the data's good
        (useful primarily when creating empty ConditionData objects)."""

        self.condition_type = condition_type   # condition model name, eg "approvalcondition" 

        self.condition_data, self.permission_data = self.reformat_front_end_data(condition_data=condition_data, permission_data=permission_data)

        if action_sourced_fields is None:
            self.action_sourced_fields = { "condition": dict(), "permission": dict() }
        else:
            self.action_sourced_fields = action_sourced_fields

        # create a condition object & populate it with condition_data, but don't save it to the database
        if self.condition_type:
            condition_class = self.get_condition_type_class()
            self.condition_object = condition_class(**self.condition_data)

        self.target_type = target_type

        if validate:
            self.validate_condition()

    def describe(self):
        if not self.condition_type:
            return "empty condition"
        else:
            return "%s condition" % self.condition_type

    def get_action_sourced_field_names(self, field_on="condition"):
        return list(self.action_sourced_fields[field_on].keys())

    def validate_condition(self):

        if not self.condition_type:
            raise ValidationError(message="Must supply condition_type to ConditionData field.")

        exclude = self.get_action_sourced_field_names(field_on="condition")
        if not self.condition_object.action:
            exclude.append("action")
        self.condition_object.clean_fields(exclude=exclude) 

        self.validate_permission_data(self.permission_data)

        if self.target_type and self.target_type not in ["gov", "own"]:
            raise ValidationError(message="Target type must be 'gov', 'own' or 'none', not " + str(self.target_type))

    def get_condition_type_class(self):       
        conditionals_module = importlib.import_module("concord.conditionals.models")
        conditional_models = inspect.getmembers(conditionals_module)
        for model_tuple in conditional_models:
            if model_tuple[0].lower() == self.condition_type.lower():
                return model_tuple[1]
        raise LookupError("No model of type " + self.condition_type.lower() + " found in conditionals.models.")

    def validate_permission_data(self, permission_data):
        """Permission_data should correspond to permission fields in the condition object and should be formatted
        with structure: { "approve_roles" : ["friends", "romans", "countrymen" ], "approve_actors" : [2,3,4] } """
        
        # reformat permission_data if needed
        throwaway, permission_data = self.reformat_front_end_data(permission_data=permission_data)

        # get action-sourced variables to exclude
        exclude_fields = self.get_action_sourced_field_names(field_on="permission")

        for field_name, field_data in permission_data.items():
            if field_name in self.condition_object.get_configurable_field_names():

                if field_name in exclude_fields:
                    continue    

                field_type = field_name.split("_")[1]
                if type(field_data) != list:
                    raise ValidationError(message="Permission field " + field_name + " must format data as list, not " + str(type(field_data)))
                if field_type == "roles":
                    if not all(type(role) == str for role in field_data):
                        raise ValidationError(message="Permission role field " + field_name + " must be list of strings.")
                if field_type == "actors":
                    if not all(type(actor) == int for actor in field_data):
                        raise ValidationError(message="Permission actor field " + field_name + " must be list of integers.")
            else:
                raise ValidationError(message="Permission field " + field_name + " cannot be set on condition " + self.condition_type)

        return permission_data

    # Reformat helpers (useful when data is passed in from front-end)

    def reformat_front_end_data(self, data=None, condition_data=None, permission_data=None):

        if data and not(condition_data or permission_data):
            condition_data = data.get("condition_data", None)
            permission_data = data.get("permission_data", None)

        if condition_data:
            if type(condition_data) == str:
                condition_data = json.loads(condition_data)
            needs_reformatting = all("type" in item for item in condition_data)
            if needs_reformatting:
                condition_data = self.reformat_condition_data(condition_data)
        else:
            condition_data = {}

        if permission_data:
            if type(permission_data) == str:
                permission_data = json.loads(permission_data)
            needs_reformatting = all("type" in item for item in permission_data)
            if needs_reformatting:
                permission_data = self.reformat_permission_data(permission_data)
        else:
            permission_data = {}

        return condition_data, permission_data

    def reformat_condition_data(self, condition_data):
        """ Data is saved as a dictionary of key-value pairs, but on the front end we often provide additional metadata
        about our fields via the helper methods get_configurable_fields and get_configurable_fields_with-data.  This
        method take configurable field data and turns it back into key-value pairs."""
    
        new_condition_data = {}
        for item in condition_data:
            if item['type'] == "BooleanField":
                if item['value'] == None:
                    continue   # Boolean fields can't store null values, so keep whatever default the db provides
                item['value'] = True if item['value'] == "true" else item['value']
                item['value'] = False if item['value'] == "false" else item['value']
            if item['type'] in ["FloatField", "IntegerField"]: # Should probably treat floatfield differently
                item['value'] = int(item['value'])  # FIXME: implement try/catch and return as error?
            new_condition_data.update({ item['name'] : item['value'] })
        
        return new_condition_data

    def reformat_permission_data(self, permission_data):
        """Data is saved as dict with structure { Changes.Conditionals.AddVote + "_actors" : value }, but often
        recieved from the front end with structure:
            [{'name': 'Roles who can vote', 'type': 'PermissionRoleField', 'required': False, 'value': 'romans',
              'field_name': 'vote_roles'}]  """

        new_permission_data = {}
        for item in permission_data:
            if item["value"] in [None, []]:
                continue   # Don't save empty values
            new_permission_data.update({ item["field_name"]: item["value"] })
        return new_permission_data

    # Get methods

    def get_condition_description(self):
        return "on the condition that " + self.condition_object.description_for_passing_condition(fill_dict=self.permission_data)

    def get_configurable_fields_with_data(self):

        field_list = []        

        for field_name, field in self.condition_object.configurable_fields().items():
            if field["type"] in ["PermissionRoleField", "PermissionActorField"]:
                if field["field_name"] in self.permission_data:
                    field["value"] = self.permission_data[field["field_name"]]
            else:
                if field_name in self.condition_data:
                    field["value"] = self.condition_data[field_name]
            field_list.append(field)

        return field_list

    # Update methods

    def update_condition_data(self, condition_data):
        """Takes in data, typically from the front, and reformats into key-value pairs using reformat_front_end_data."""
        self.condition_data, throwaway = self.reformat_front_end_data(condition_data=condition_data)
        condition_class = self.get_condition_type_class()
        self.condition_object = condition_class(**self.condition_data)
        self.validate_condition()

    def update_permission_data(self, permission_data):
        throwaway, self.permission_data = self.reformat_front_end_data(permission_data=permission_data)
        self.validate_condition()

    def get_action_data(self, action, data_to_get):
        """Helper method to get data from a given action, to replace action-sourced-fields in condition and the permissions
        set on the condition."""
        if data_to_get["replacement field"] == "actor":
            return action.actor
        if data_to_get["replacement field"] == "target":
            return action.target
        if data_to_get["replacement field"] == "created_at":
            return action.created_at
        if data_to_get["replacement field"] == "change_type":
            return action.change.get_change_type()
        if data_to_get["replacement field"] == "change_parameter":
            # assumes we want ALL the data from a single parameter, and ONLY a single parameter
            return getattr(action.change, data_to_get["additional data"])

    def replace_action_sourced_fields_with_real_data(self, action):
        """Occasionally we want something about a condition (and its associated permissions) to be dependent on the
        action which generated it (though we use the term 'sourced' here to not be confused with actions in a container,
        which depend on the result of the previous action). For example, when setting new members as 'invite only' we want 
        only the person in member_pk_list in action.change.data to have permission to approve the condition generated by 
        the action. After all, no one should be able to accept an invite on behalf of someone else.

        To handle this, condition_data and permission_data can both accept empty (None) parameters in condition data 
        and permission data. A corresponding entry *must* be placed in action_sourced_fields, which has format:

        { "condition" : { "field_name": { "replacement field": , "additional data" : {} }, 
            "permission" : "field_name": { "replacement field": , "additional data" : {} } }  }

        Valid action fields to replace with include: actor, target, created_at, change_type, change_parameters.  Change_parameters
        uses that additional_data key to supply the specific parameter to replace with."""
        
        # first replace fields on condition object
        for field_name, data in self.action_sourced_fields["condition"].items():
            setattr(self.condition_object, field_name, self.get_action_data(action, data))

        # then replace fields within self.permission_data
        for field_name, data in self.action_sourced_fields["permission"].items():
            self.permission_data[field_name] = self.get_action_data(action, data)

    def create_condition_and_permissions(self, action, owner):
        """Creates a condition object & associated permissions from the template."""

        self.replace_action_sourced_fields_with_real_data(action)

        self.condition_object.action = action.pk
        self.condition_object.owner = owner
        self.condition_object.save()
        new_condition_object = self.condition_object

        from concord.permission_resources.utils import create_permissions_outside_pipeline
        create_permissions_outside_pipeline(self.permission_data, self.condition_object, owner)

        # clear the condition object just in case
        condition_class = self.get_condition_type_class()
        self.condition_object = condition_class(**self.condition_data) 

        return new_condition_object


class UnvalidatedConditionData(ConditionData):
    """"There's probably a better way to do this, but I wanted to validate input by default while still allowing
    us to create empty ConditionDatas on new ConditionTemplate models."""

    def __init__(self, *, condition_type=None, condition_data=None, permission_data=None, target_type=None, validate=False):
        super().__init__(condition_type=condition_type, condition_data=condition_data, permission_data=permission_data,
            target_type=target_type, validate=validate)  


####################
### Custom Field ###
####################


def parse_condition_data(data):
    data_from_db = json.loads(data)
    return ConditionData(condition_type=data_from_db["condition_type"], condition_data=data_from_db["condition_data"],
        permission_data=data_from_db["permission_data"], action_sourced_fields=data_from_db["action_sourced_fields"],
        target_type=data_from_db["target_type"])


class ConditionDataField(models.Field):
    """This custom field allows us to access the methods and validation of the ConditionData
    object."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar' 

    def from_db_value(self, value, expression, connection):
        if value is None:
            return ConditionData(validate=False)
        return parse_condition_data(value)

    def to_python(self, value):
        if isinstance(value, ConditionData):
            return value
        if value is None:
            return ConditionData(validate=False)
        return parse_condition_data(value)

    def get_prep_value(self, value):
        if isinstance(value, ConditionData):
            return json.dumps({
                "condition_type": value.condition_type,
                "condition_data": value.condition_data,
                "permission_data": value.permission_data,
                "action_sourced_fields": value.action_sourced_fields,
                "target_type": value.target_type
            })
