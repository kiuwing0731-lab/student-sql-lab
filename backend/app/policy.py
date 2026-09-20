"""Conservative PostgreSQL AST policy. Database roles remain the isolation boundary."""
import json
from pglast import parser, split

ALLOWED = {'SelectStmt','InsertStmt','UpdateStmt','DeleteStmt','CreateStmt',
           'IndexStmt','ViewStmt','AlterTableStmt','DropStmt','TruncateStmt'}
FUNCTIONS = set("count sum avg min max abs round ceil ceiling floor mod power sqrt length char_length lower upper trim btrim ltrim rtrim substring substr replace concat concat_ws coalesce nullif greatest least now date_trunc date_part age to_char to_date to_timestamp extract string_agg array_agg json_agg jsonb_agg json_build_object jsonb_build_object row_number rank dense_rank lag lead first_value last_value nth_value ntile percent_rank cume_dist generate_series unnest array_length cardinality jsonb_array_elements jsonb_each jsonb_extract_path_text left right position split_part octet_length bool_and bool_or every stddev variance random setseed".split())
TYPES = set('int int2 int4 int8 integer smallint bigint serial serial2 serial4 serial8 smallserial bigserial text varchar bpchar char boolean bool numeric decimal real float4 float8 double date time timestamp timestamptz timetz interval json jsonb uuid bytea'.split())

class PolicyError(ValueError): pass

def validate(source, maximum=1):
    try:
        tree=json.loads(parser.parse_sql_json(source))
        statements=list(split(source))
    except Exception as exc:
        raise PolicyError('Invalid PostgreSQL SQL: '+str(exc)) from exc
    nodes=tree.get('stmts',[])
    if not nodes or len(nodes)>maximum:
        raise PolicyError(f'Use between 1 and {maximum} statements.')
    def walk(value):
        if isinstance(value,list):
            for child in value: walk(child)
        elif isinstance(value,dict):
            if 'relname' in value and (value.get('catalogname') or value.get('schemaname','public')!='public' or value['relname'].lower().startswith(('pg_','sql_'))):
                raise PolicyError('Only tables in your public schema are available.')
            for kind,node in value.items():
                if kind[:1].isupper() and kind.endswith('Stmt') and kind not in ALLOWED:
                    raise PolicyError(f'{kind} is not supported in this classroom sandbox.')
                if kind=='FuncCall':
                    names=[p['String']['sval'] for p in node['funcname']]
                    if len(names)!=1 or names[0].lower() not in FUNCTIONS:
                        raise PolicyError('Function is not on the classroom allowlist.')
                if kind=='RangeVar':
                    if node.get('catalogname') or node.get('schemaname','public')!='public' or node.get('relname','').lower().startswith(('pg_','sql_')):
                        raise PolicyError('Only tables in your public schema are available.')
                if kind in ('TypeName','typeName'):
                    names=[p['String']['sval'] for p in node.get('names',[])]
                    if not names or names[-1] not in TYPES or (len(names)>1 and names[:-1]!=['pg_catalog']):
                        raise PolicyError('Unsupported data type.')
                if kind=='DropStmt' and node.get('removeType') not in ('OBJECT_TABLE','OBJECT_VIEW','OBJECT_INDEX'):
                    raise PolicyError('Only tables, views and indexes can be dropped.')
                if kind=='AlterTableCmd' and node.get('subtype') not in ('AT_AddColumn','AT_DropColumn','AT_ColumnDefault','AT_SetNotNull','AT_DropNotNull','AT_AlterColumnType','AT_AddConstraint','AT_DropConstraint'):
                    raise PolicyError('Unsupported ALTER TABLE operation.')
                if kind in ('CreateStmt','IndexStmt') and (node.get('tablespacename') or node.get('options')):
                    raise PolicyError('Storage options are not supported.')
                if kind=='IndexStmt' and node.get('accessMethod','btree')!='btree':
                    raise PolicyError('Only btree indexes are supported.')
                if kind in ('returningList','returningClause') and node:
                    raise PolicyError('Use a separate SELECT instead of RETURNING.')
                if kind=='intoClause' and node:
                    raise PolicyError('SELECT INTO is disabled; use CREATE TABLE then INSERT.')
                walk(node)
    walk(tree)
    return statements
