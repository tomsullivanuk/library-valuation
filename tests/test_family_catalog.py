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

def test_explicit_book_description_is_searchable_and_escaped_without_private_notes():
 scope=CompletedInventoryScope(completed=True,catalog_item_ids=('BK1',))
 records=project([row()],scope,{'BK1':'Scholarly cosmology <img src=x onerror=alert(1)>','OTHER':'OUTSIDE_SCOPE'})
 page=render(records,'DATE')
 assert records[0]['description'].startswith('Scholarly cosmology')
 assert 'Book description' in page and 'Scholarly cosmology' in page
 assert '<img src=x' not in page and '&lt;img' in page
 assert all(secret not in page for secret in ['PRIVATE_NOTE','PRIVATE_DESCRIPTION','PRIVATE_COST','PRIVATE_VALUE','PRIVATE_BOX','OUTSIDE_SCOPE'])
 assert 'Pops Sullivan' in page and 'id="signed-in"' in page
 assert '<h1>Thomas D Sullivan Library</h1>' in page
 assert 'Pops will confirm availability and arrange delivery with you.' in page
 assert page.index('id="search-tools"') < page.index('id="count"') < page.index('Catalog updated')
