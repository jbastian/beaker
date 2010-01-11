import model
import re
from sqlalchemy import or_, and_, not_
from turbogears.database import session

import logging
log = logging.getLogger(__name__)

class MyColumn(object):
    """
    MyColumn is a class to hold information about a mapped column, 
    such as the actual mapped column, the type, and a relation it may
    have to another mapped object

    It should be overridden by classes that will consistently use a 
    relation to another mapped object.
    """
    def __init__(self,relations=None,col_type=None,column = None):        
        if type(col_type) != type(''):
            raise TypeError('col_type var passed to %s must be string' % self.__class__.__name__)
        
        if relations is not None:
            if type(relations) != type([]) and type(relations) != type(''):
                raise TypeError('relation var passed to %s must be of type list of string' % self.__class__.__name__)
        
        self._column = column
        self._type = col_type
        self._relations = relations
        
    @property    
    def type(self):
        return self._type   
    
    @property
    def relations(self):
        return self._relations
    
    @property
    def column(self):
        return self._column
    
class CpuColumn(MyColumn):
    """
    CpuColumn defines a relationship to system
    """
    def __init__(self,**kw):
        if not kw.has_key('relations'):
            kw['relations'] = 'cpu'
        super(CpuColumn,self).__init__(**kw)
        
class DeviceColumn(MyColumn):
    """
    DeviceColumn defines a relationship to system
    """
    def __init__(self,**kw):
        if not kw.has_key('relations'):
            kw['relations'] = 'devices'
        super(DeviceColumn,self).__init__(**kw)        
    
class KeyColumn(MyColumn):
    """
    KeyColumn defines a relationship to system for either a string or int 
    type key
    """
    def __init__(self,**kw):
        try:
            if type(kw['relations']) != type([]):
                raise TypeError('relations var passed to MyColumn must be a list')
        except KeyError, (error):
            log.error('No relations passed to KeyColumn')
        else:  
            self._column = None 
            if not kw.get('int_column'):      
                self._int_column = model.key_value_int_table.c.key_value
            if not kw.get('string_column'):
                self._string_column = model.key_value_string_table.c.key_value
                
            self._type = None
            self._relations = kw['relations']
            
    @property
    def int_column(self):
        return self._int_column
    
    @property
    def string_column(self):
        return self._string_column
    
    def set_column(self,val):
        self._column = val
        
    def set_type(self,val):
        self._type = val
        
class Modeller(object):
    """ 
    Modeller class provides methods relating to different datatypes and 
    operations available to those datatypes
    """ 
    def __init__(self):
        self.structure = {'string' : {'is' : lambda x,y: self.equals(x,y),
                                       'is not' : lambda x,y: self.not_equal(x,y),
                                       'contains' : lambda x,y: self.contains(x,y), },

                          'text' : {'is' : lambda x,y: self.equals(x,y),
                                        'is not' : lambda x,y: self.not_equal(x,y),
                                        'contains' : lambda x,y: self.contains(x,y), },
                                               
                          'integer' : {'is' : lambda x,y: self.equals(x,y), 
                                       'is not' : lambda x,y: self.not_equal(x,y),
                                       'less than' : lambda x,y: self.less_than(x,y),
                                       'greater than' : lambda x,y: self.greater_than(x,y), },
                             
                          'unicode' : {'is' : lambda x,y: self.equals(x,y),
                                       'is not' : lambda x,y: self.not_equal(x,y),
                                       'contains' : lambda x,y: self.contains(x,y), },
                          
                          'boolean' : {'is' : lambda x,y: self.bool_equals(x,y),
                                       'is not' : lambda x,y: self.bool_not_equal(x,y), },  
                          
                          'datetime' : {'before' : lambda x,y: self.less_than(x,y),
                                        'after'  : lambda x,y: self.greater_than(x,y),},

                          'generic' : {'is' : lambda x,y: self.equals(x,y) ,
                                       'is not': lambda x,y:  self.not_equal(x,y), },
                         } 
 
    def less_than(self,x,y):
        return x < y

    def greater_than(self,x,y):
        return x > y
 
    def bool_not_equal(self,x,y):
        bool_y = int(y)
        return x != bool_y

    def bool_equals(self,x,y): 
        bool_y = int(y) 
        return x == bool_y

    def not_equal(self,x,y): 
        if not y:
            return and_(x != None,x != y)
        return or_(x != y, x == None)

    def equals(self,x,y):    
        if not y:
            return or_(x == None,x==y)
        return x == y

    def contains(self,x,y): 
        return x.like('%%%s%%' % y )
 
    def return_function(self,type,operator,loose_match=True):
        """
        return_function will return the particular python function to be applied to a type/operator combination 
        (i.e sqlalchemy.types.Integer and 'greater than')
        """
        try:
            op_dict = self.structure[type]   
        except KeyError, (error):
            if loose_match:
                op_dict = self.loose_type_match(type)
            
            if not op_dict:
                log.debug('Could not access specific type operator functions for %s in return_function, will use generic' % error)
                op_dict = self.structure['generic']
       
        return op_dict[operator]        

    def return_operators(self,field_type,loose_match=True): 
        # loose_match flag will specify if we should try and 'guess' what data type it is 
        # int,integer,num,number,numeric will match for an integer.
        # string, word match for sqlalchemy.types.string
        # bool,boolean will match for sqlalchemy.types.boolean
        operators = None
        field_type = field_type.lower()
        try:
            operators = self.structure[field_type] 
        except KeyError, (error):
            if loose_match: 
                operators = self.loose_type_match(field_type)    
            if operators is None:
                operators = self.structure['generic']
                log.debug('Could not access specific type operators for %s, will use generic' % error)
           
        return operators.keys() 
          
    def loose_type_match(self,field_type):
        type_lower = field_type.lower()
        int_pattern = '^int(?:eger)?$|^num(?:ber|eric)?$'  
        string_pattern = '^string$|^word$'          
        bool_pattern = '^bool(?:ean)?$'
        operators = None
        if re.match(int_pattern,type_lower):
            operators = self.structure['integer']
        elif re.match(string_pattern,type_lower):
            operators = self.structure['string']
        elif re.match(bool_pattern,type_lower):
            operators = self.structure['boolean']
        return operators
        
class Search:
    def return_results(self): 
        return self.queri        

    def do_joins(self,mycolumn):
        if mycolumn.relations:
            try:    
                #This column has specified it needs a join, so let's add it to the all the joins
                #that are pertinent to this class. We do this so there is only one point where we add joins 
                #to the query
                #cls_ref.joins.add_join(col_string = str(column),join=mycolumn.join)
                relations = mycolumn.relations
                if type(relations) == type(''):
                    self.queri = self.queri.outerjoin(relations,aliased=True)    
		else:    
		    for relation in relations:
			if type(relation) == type([]):
                            self.queri = self.queri.outerjoin(relation,aliased=True)    
                        else:
                            self.queri = self.queri.outerjoin(relations,aliased=True)
                            break     
                        
            except TypeError, (error):
                log.error('Column %s has not specified joins validly:%s' % (column, error))                                                               

    def return_standard_filter(self,mycolumn,operation,value,loose_match=True): 
        col_type = mycolumn.type
        modeller = Modeller() 
        filter_func = modeller.return_function(col_type,operation,loose_match=True)   
        return lambda: filter_func(mycolumn.column,value)

    def pre_operations(self,column,operation,value,cls_ref=None,**kw):
        #First let's see if we have a column X operation specific filter
        #We will only need to use these filter by table column if the ones from Modeller are 
        #inadequate. 
        #If we are looking at the System class and column 'arch' with the 'is not' operation, it will try and get
        # System.arch_is_not_filter
        if cls_ref is None:          
            match_obj = re.search('^(.+)?Search$',self.__class__.__name__) 
            cls_ref = globals()[match_obj.group(1)]
            if cls_ref is None:
                raise BeakerException('No cls_ref passed in and class naming convetion did give valid class')
        results_dict = {}
        underscored_operation = re.sub(' ','_',operation) 
        column_match = re.match('^(.+)?/(.+)?$',column)
        try:
            if column_match.group():
                #if We are searchong on a searchable_column that is something like 'System/Name' 
                #and the 'is not' operation, it will look for the SystemName_is_not_filter method
                column_mod = '%s%s' % (column_match.group(1).capitalize(),column_match.group(2).capitalize()) 
        except AttributeError, (error):
            column_mod = column.lower()
         
        col_op_filter = getattr(cls_ref,'%s_%s_filter' % (column_mod,underscored_operation),None)
        results_dict.update({'col_op_filter':col_op_filter})         
        #At this point we can also call a custom function before we try to append our results
        
        col_op_pre = getattr(cls_ref,'%s_%s_pre' % (column_mod,underscored_operation),None)           
        if col_op_pre is not None:
            results_dict.update({'results_from_pre': col_op_pre(value,col=column,op = operation, **kw)})  
        return results_dict 
         
    @classmethod 
    def search_on(cls,field,cls_ref=None): 
        """
        search_on() takes the field name we will search by, and
        returns the operations suitable for the field type it represents
        """
        if cls_ref is None:          
            match_obj = re.search('^(.+)?Search$',cls.__name__) 
            cls_ref = globals()[match_obj.group(1)]
            if cls_ref is None:
                raise BeakerException('No cls_ref passed in and class naming convetion did give valid class')          
        try:
            field_type = cls_ref.get_field_type(field) 
            vals = None
            try:
                vals = cls_ref.search_values(field)
            except AttributeError:
                log.debug('Not using predefined search values for %s->%s' % (cls_ref.__name__,field))  
        except AttributeError, (error):
            log.error('Error accessing attribute within search_on: %s' % (error))
        else:
            return dict(operators = cls_ref.search_operators(field_type), values=vals)

    @classmethod 
    def field_type(cls,field): 
       """ 
       Takes a field string (ie'Processor') and returns the type of the field
       """  
       match_obj = re.search('^(.+)?Search$',cls.__name__) 
       cls_ref = globals()[match_obj.group(1)]  
  
       field_type = cls_ref.get_field_type(field)  
       if field_type:
           return field_type
       else:
           log.debug('There was a problem in retrieving the field_type for the column %s' % field)
           return

    @classmethod
    def translate_name(cls,display_name):
        """ 
        translate_name() get's a reference to the class from it's display name 
        """
        try:
            class_ref = cls.class_external_mapping[display_name]
        except KeyError:
            log.error('Class %s does not have a mapping to display_name %s' % (cls.__name__,display_name))
            raise
        else:
           return class_ref

    @classmethod
    def split_class_field(cls,class_field):
        class_field_list = class_field.split('/')     
        display_name = class_field_list[0]
        field = class_field_list[1] 
        return (display_name,field)

    @classmethod
    def create_search_table(cls,cls_to_search): 
        searchable = cls_to_search.get_searchable()
        searchable.sort()
        return searchable    

class ActivitySearch(Search):
    search_table = [] 
    def __init__(self,activity):
        self.queri = activity
   
    def append_results(self,value,column,operation,**kw):
        pre = self.pre_operations(column,operation,value,**kw)
        mycolumn = Activity.searchable_columns.get(column) 
        if mycolumn:
            self.do_joins(mycolumn)
        else:
            log.error('Error accessing attribute within %s.append_results' % self.__class__.__name__)
       
        if pre['col_op_filter']:
            filter_func = pre['col_op_filter']
            filter_final = lambda: filter_func(mycolumn.column,value)
        else: 
            filter_final = self.return_standard_filter(mycolumn,operation,value)
        self.queri = self.queri.filter(filter_final())   
      
class HistorySearch(Search):
    search_table = []
     
    def __init__(self,activity):
        self.queri = activity 
 
    def append_results(self,value,column,operation,**kw):
        pre = self.pre_operations(column,operation,value,**kw)
        mycolumn = History.searchable_columns.get(column) 
        if mycolumn:
            self.do_joins(mycolumn)
        else:
            log.error('Error accessing attribute within %s.append_results' % self.__class__.__name__)
       
        if pre['col_op_filter']:
            filter_func = pre['col_op_filter']
            filter_final = lambda: filter_func(mycolumn.column,value)
        else: 
            filter_final = self.return_standard_filter(mycolumn,operation,value)
        self.queri = self.queri.filter(filter_final())   

class SystemSearch(Search): 
    class_external_mapping = {}
    search_table = []
    
    def __init__(self, systems=None):
        if systems:
            self.queri = systems
        else:
            self.queri = session.query(model.System)
 
    def __getitem__(self,key):
        pass

    def append_results(self,cls_ref,value,column,operation,**kw):  
        """ 
        append_results() will take a value, column and operation from the search field,
        as well as the class of which the search pertains to, and will append the join
        and the filter needed to return the correct results.   
        """     
        pre = self.pre_operations(column,operation,value,cls_ref,**kw)
        mycolumn = cls_ref.searchable_columns.get(column)
        if mycolumn:
            if cls_ref is Key:    
                if pre['results_from_pre'] == 'string':
                    mycolumn.set_column(mycolumn.string_column)
                    mycolumn.set_type('string')
                elif pre['results_from_pre'] == 'int':
                    mycolumn.set_column(mycolumn.int_column)
                    mycolumn.set_type('int')
                else:
                    log.error('Expecting the string value \'string\' or \'int\' to be returned from col_op_pre function when searching on Key/Value');       
            self.do_joins(mycolumn)
        else:       
            log.error('Error accessing attribute within append_results')
                   
        if pre['col_op_filter']:
            filter_func = pre['col_op_filter']   
            filter_final = lambda: filter_func(mycolumn.column,value)
            #If you want to pass custom args to your custom filter, here is where you do it
            if kw.get('keyvalue'): 
                filter_final = lambda: filter_func(mycolumn.column,value,key_name=kw['keyvalue'])   
        else:
            #using just the regular filter operations from Modeller 
            filter_final = self.return_standard_filter(mycolumn,operation,value) 
                                   
        self.queri = self.queri.filter(filter_final())
       

    @classmethod 
    def field_type(cls,class_field): 
       """ 
       Takes a class/field string (ie'CPU/Processor') and returns the type of the field
       """
       returned_class_field = cls.split_class_field(class_field) 
       display_name = returned_class_field[0]
       field = returned_class_field[1]        
      
       class_ref = cls.translate_name(display_name)
       field_type = class_ref.get_field_type(field)  
       
       if field_type:
           return field_type
       else:
           log.debug('There was a problem in retrieving the field_type for the column %s' % field)
           return

    @classmethod
    def search_on_keyvalue(cls,key_name):
        """
        search_on_keyvalue() takes a key_name and returns the operations suitable for the 
        field type it represents
        """
        row = model.Key.by_name(key_name) 
        if row.numeric == 1:
            field_type = 'Numeric'
        elif row.numeric == 0:
            field_type = 'String'        
        else:
            log.error('Cannot determine type for %s, defaulting to generic' % key_name)
            field_type = 'generic'

        return Key.search_operators(field_type,loose_match=True)
        
             
    @classmethod 
    def search_on(cls,class_field): 
        """
        search_on() takes a combination of class name and field name (i.e 'Cpu/vendor') and
        returns the operations suitable for the field type it represents
        """ 
        returned_class_field = cls.split_class_field(class_field) 
        display_name = returned_class_field[0]
        field = returned_class_field[1]        
        class_ref = cls.translate_name(display_name)
        
        try:
            field_type = class_ref.get_field_type(field) 
            vals = None
            try:
                vals = class_ref.search_values(field)
            except AttributeError:
                log.debug('Not using predefined search values for %s->%s' % (class_ref.__name__,field))  
        except AttributeError, (error):
            log.error('Error accessing attribute within search_on: %s' % (error))
        else:
            return dict(operators=class_ref.search_operators(field_type), values=vals)
       
    @classmethod
    def create_search_table(cls,searchable_objs):  
        """
        create_search_table will set and return the class' search_table class attribute with
        a list of searchable 'combinations'.
        These 'combinations' merely represent a table and a column.
        An example of search_table entry may be 'CPU/Vendor' or 'System/Name'
        """ 
        #Clear the table if it's already been created
        if cls.search_table != None:
            cls.search_table = []
        
        for obj in searchable_objs:  
            #Check if we have a specialised display name
            display_name = getattr(obj,'display_name',None)
            if display_name != None:
                display_name = obj.display_name
                  
                #If the display name is already being used by some class.
                if cls.class_external_mapping.has_key(display_name): 
                    log.debug("Display name %s cannot be set for %s display name will be set to class name" % (display_name, obj.__name__))
                    display_name = obj.__name__                    
            else:
                display_name = obj.__name__
              
            #We have our final display name, if it still exists in the mapping
            #there isn't much we can do, and we don't want to overwrite it.
            if cls.class_external_mapping.has_key(display_name): 
                log.error("Display name %s cannot be set for %s" % (display_name,obj.__name__))               
            else: 
                cls.class_external_mapping[display_name] = obj

            #Now let's actually build the search table
            searchable =  obj.get_searchable() 
            for item in searchable: 
                 cls.search_table.append('%s/%s' % (display_name,item))  
               
        cls.search_table.sort()
        return cls.search_table

class SystemObject:
    @classmethod
    def get_field_type(cls,field):
        mycolumn = cls.searchable_columns.get(field)
        if mycolumn:
            try:
                field_type = mycolumn.type 
                return field_type
            except AttributeError, (error):
                log.error('No type specified for %s in searchable_columns:%s' % (field,error))
        else:
            log.error('Column %s is not a mapped column nor is it part of searchable_columns' % field)
                    
    @classmethod
    def search_values(cls,col):  
       if cls.search_values_dict.has_key(col):
           return cls.search_values_dict[col]
       
    @classmethod
    def get_searchable(cls):
        """
        get_searchable will return the description of how the calling class can be searched by returning a list
        of fields that can be searched after any field filtering has
        been applied
        """
        try:           
            return [k for (k,v) in cls.searchable_columns.iteritems()]
        except AttributeError,(e):
            log.debug('Unable to access searchable_columns of class %s' % cls.__name__)
            return []
    
    @classmethod
    def search_operators(cls,field):
        """
        search_operators returns a list of the different types of searches that can be done on a given field.
        It relies on the Modeller class, which stores these relationships.
        """             
        m = Modeller() 
    
        try:                  
            return m.return_operators(field)
        except KeyError, (e): 
            log.error('Failed to find search_type by index %s, got error: %s' % (index_type,e))
            
class System(SystemObject): 
    search_table = []
    searchable_columns = {'Vendor'    : myColumn(column=model.System.vendor,col_type='string'),
                          'Name'      : myColumn(column=model.System.fqdn,col_type='string'),
                          'Lender'    : myColumn(column=model.System.lender,col_type='string'),
                          'Model'     : myColumn(column=model.System.model,col_type='string'),
                          'Memory'    : myColumn(column=model.System.memory,col_type='numeric'),
                          'User'      : myColumn(column=model.User.user_name, col_type='string', system_relation='user'),
                          'Owner'     : myColumn(column=model.User.user_name, col_type='string', system_relation='owner'),
                          'Status'    : myColumn(column=model.SystemStatus.status, col_type='string', system_relation='status'),
                          'Arch'      : myColumn(column=model.Arch.arch, col_type='string', system_relation='arch'),
                          'Type'      : myColumn(column=model.SystemType.type, col_type='string', system_relation='type'),
                          'PowerType' : myColumn(column=model.PowerType.name, col_type='string', system_relation=['power','power_type'])
                         }  
    search_values_dict = {'Status' : lambda: model.SystemStatus.get_all_status_name(),
                          'Type' : lambda: model.SystemType.get_all_type_names() }   
    
    @classmethod
    def arch_is_not_filter(cls,col,val):
        """
        arch_is_not_filter is a function dynamically called from append_results.
        It serves to provide a table column operation specific method of filtering results of System/Arch
        """       
        if not val: 
           return or_(col != None, col != val) 
        else:
            #If anyone knows of a better way to do this, by all means...
            query = model.System.query().filter(model.System.arch.any(model.Arch.arch == val))       
          
        ids = [r.id for r in query]  
        return not_(model.system_table.c.id.in_(ids)) 
           
    @classmethod
    def search_values(cls,col):  
       if cls.search_values_dict.has_key(col):
           return cls.search_values_dict[col]() 
       
class Activity(SystemObject):
    search = ActivitySearch    
    searchable_columns = { 
                           'User' : MyColumn(col_type='string', column=model.User.user_name, relations='user'),
                           'Via' : MyColumn(col_type='string', column=model.Activity.service),
                           'System/Name' : MyColumn(col_type='string', column=model.System.fqdn, relations='object'),
                           'System/Arch' : MyColumn(col_type='string', column=model.Arch.arch, relations=['object','arch']),
                           'Property': MyColumn(col_type='string', column=model.Activity.field_name),
                           'Action' : MyColumn(col_type='string', column=model.Activity.action),
                           'Old Value' : MyColumn(col_type='string', column=model.Activity.old_value),
                           'New Value' : MyColumn(col_type='string', column=model.Activity.new_value),
                         }  

    @classmethod
    def SystemArch_is_not_filter(cls,col,val):
        """
        SystemArch_is_not_filter provides a custom filter for the System/Arch search.
        """
        if not val: 
           return or_(col != None, col != val) 
        else: 
            query = model.SystemActivity.query().join(['object','arch']).filter(model.Arch.arch == val)          
        ids = [r.id for r in query]  
        return not_(model.activity_table.c.id.in_(ids)) 
        

class History(SystemObject): 
    search = HistorySearch
    searchable_columns = {
                          'PUser' : MyColumn(col_type='string', column=model.User.user_name,relations='user'),
                          'Service' : MyColumn(col_type='string', column=model.Activity.service),
                          'Field Name' : MyColumn(col_type='string', column=model.Activity.field_name),
                          'Action' : MyColumn(col_type='string', column=model.Activity.action),
                          'Old Value' : MyColumn(col_type='string', column=model.Activity.old_value),
                          'New Value' : MyColumn(col_type='string', column=model.Activity.new_value) 
                         }  
       
class Key(SystemObject):
    searchable_columns = {'Value': KeyColumn(relations=[['key_values_int','key'],['key_values_string','key']])}
    
    @classmethod
    def search_operators(cls,type,loose_match=None):
        m = Modeller()
        operators = m.return_operators(type,loose_match)    
        return operators
     
    @classmethod
    def value_pre(cls,value,**kw): 
        if not kw.get('keyvalue'):
            raise Exception, 'value_pre needs a keyvalue. keyvalue not found' 
        result = model.Key.by_name(kw['keyvalue']) 
        int_table = result.numeric
        key_id = result.id
        if int_table == 1:
            return 'int'    
        elif int_table == 0:
            return 'string'
        else:
            log.error('Unexpected result %s from value_pre in class %s' % (int_table,cls.__name__))
             
    @classmethod
    def value_is_pre(cls,value,**kw): 
       return cls.value_pre(value,**kw)

    @classmethod
    def value_is_not_pre(cls,value,**kw):
        return cls.value_pre(value,**kw)
 
    @classmethod
    def value_less_than_pre(cls,value,**kw):
        return cls.value_pre(value,**kw)

    @classmethod
    def value_greater_than_pre(cls,value,**kw):
        return cls.value_pre(value,**kw)
    
    @classmethod
    def value_contains_pre(cls,value,**kw):
        return cls.value_pre(value,**kw)
    
    @classmethod
    def value_greater_than_filter(cls,col,val,key_name):
        result = model.Key.by_name(key_name) 
        int_table = result.numeric
        key_id = result.id
        return and_(model.Key_Value_Int.key_value > val, model.Key_Value_Int.key_id == key_id)

    @classmethod
    def value_contains_filter(cls, col, val, key_name):
        result = model.Key.by_name(key_name) 
        key_id = result.id
        return and_(model.Key_Value_String.key_value.like('%%%s%%' % val),model.Key_Value_String.key_id == key_id) 
        
    @classmethod
    def value_is_filter(cls,col,val,key_name):
        result = model.Key.by_name(key_name) 
        int_table = result.numeric
        key_id = result.id
       
        if int_table == 1:
            if not val:
                return and_(or_(model.Key_Value_Int.key_value == val,model.Key_Value_Int.key_value == None),or_(model.Key_Value_Int.key_id == key_id,model.Key_Value_Int.key_id == None))    
            else:
                return and_(model.Key_Value_Int.key_value == val,model.Key_Value_Int.key_id == key_id)
        elif int_table == 0:
            if not val:
                return and_(or_(model.Key_Value_String.key_value == val,model.Key_Value_String.key_value == None),or_(model.Key_Value_String.key_id == key_id,model.Key_Value_String.key_id == None))
            else:
                 return and_(model.Key_Value_String.key_value == val,model.Key_Value_String.key_id == key_id) 

    @classmethod
    def value_is_not_filter(cls,col,val,key_name):
        result = model.Key.by_name(key_name)
        int_table = result.numeric
        key_id = result.id
       
        if int_table == 1:
            if val:
                return and_(or_(model.Key_Value_Int.key_value != val,model.Key_Value_Int.key_value == None), or_(model.Key_Value_Int.key_id == key_id,model.Key_Value_Int.key_id == None))
            else:
                return and_(model.Key_Value_Int.key_value != val, model.Key_Value_Int.key_id == key_id)
        elif int_table == 0:
            if val:
                return and_(or_(model.Key_Value_String.key_value != val,model.Key_Value_String.key_value == None), or_(model.Key_Value_String.key_id == key_id, model.Key_Value_String.key_id == None))         
            else:
                return and_(model.Key_Value_String.key_value != val, model.Key_Value_String.key_id == key_id)
            
class Cpu(SystemObject):      
    display_name = 'CPU'   
    search_values_dict = { 'Hyper' : ['True','False'] }
    searchable_columns = {
                          'Vendor' : CpuColumn(col_type='string', column=model.Cpu.vendor),
                          'Processors' : CpuColumn(col_type='numeric',column=model.Cpu.processors),
                          'Hyper' : CpuColumn(col_type='boolean',column=model.Cpu.hyper),
                          'Cores' : CpuColumn(col_type='numeric',column=model.Cpu.cores),
                          'Sockets' : CpuColumn(col_type='numeric',column=model.Cpu.sockets),
                          'Model' : CpuColumn(col_type='numeric',column=model.Cpu.model),
                          'Flags' : CpuColumn(col_type='string',column=model.CpuFlag.flag, relations=['cpu','flags']) 
                         }  

    @classmethod
    def flags_is_not_filter(cls,col,val,**kw):
        """
        flags_is_not_filter is a function dynamically called from append_results.
        It serves to provide a table column operation specific method of filtering results of CPU/Flags
        """       
        if not val:
            return col != val
        else:
            query = model.Cpu.query().filter(model.Cpu.flags.any(model.CpuFlag.flag == val))
            ids = [r.id for r in query]
            return or_(not_(model.cpu_table.c.id.in_(ids)), col == None) 
         
class Device(SystemObject):
    display_name = 'Devices'
    searchable_columns = {'Description' : DeviceColumn(col_type='string', column=model.Device.description),
                          'Vendor_id' : DeviceColumn(col_type='string', column=model.Device.vendor_id),
                          'Device_id' : DeviceColumn(col_type='string', column=model.Device.device_id),
                          'Driver' : DeviceColumn(col_type='string', column=model.Device.driver)  } 
      
    @classmethod
    def driver_is_not_filter(cls,col,val):
        if not val:
            return or_(col != None, col != val)
        else:
            query = model.System.query().filter(model.System.devices.any(model.Device.driver == val))
    
        ids = [r.id for r in query]  
        return not_(model.system_table.c.id.in_(ids))   
