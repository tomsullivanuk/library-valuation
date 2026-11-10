from dataclasses import replace
import pytest
from valuation.completed_inventory import CompletedInventoryScope
from valuation.family_catalog import project,render,FIELDS

def row(id='BK1'):
 return dict(catalog_item_id=id,title='Title <script>alert(1)</script>',author='Author',publisher='Press',publication_year='2020',isbn13='9780198829171',isbn10='',purchase_price='PRIVATE_COST',location='PRIVATE_BOX',notes='PRIVATE_NOTE',description='PRIVATE_DESCRIPTION',valuation='PRIVATE_VALUE')

def test_physical_scope_and_private_field_exclusion():
 scope=CompletedInventoryScope(completed=True,catalog_item_ids=('BK1',))
 records=project([row(),row('HISTORICAL')],scope)
 assert len(records)==1 and set(records[0])==set(FIELDS)
 page=render(records,'DATE')
 assert not any(x in page for x in ['PRIVATE_COST','PRIVATE_BOX','PRIVATE_NOTE','PRIVATE_DESCRIPTION','PRIVATE_VALUE','HISTORICAL','BK1'])
 assert '<script>alert(1)</script>' not in page and '&lt;script&gt;' in page
 assert '1 catalog records' in page

def test_fail_closed_scope_and_identity():
 with pytest.raises(ValueError):project([row()],CompletedInventoryScope())
 scope=CompletedInventoryScope(completed=True,catalog_item_ids=('MISSING',))
 with pytest.raises(ValueError):project([row()],scope)
 with pytest.raises(ValueError):project([row(),row()],replace(scope,catalog_item_ids=('BK1',)))
 with pytest.raises(ValueError):render([{'notes':'PRIVATE'}],'DATE')
