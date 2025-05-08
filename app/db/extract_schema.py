import sqlite3
import os

def get_schema():
    # Get the database path
    db_path = os.path.join(os.path.dirname(__file__), 'mcq_database.db')
    
    # Connect to the database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = cursor.fetchall()
    
    schema_text = "# Database Schema for PediaMCQ\n\n"
    
    # Process each table
    for table in tables:
        table_name = table[0]
        if table_name.startswith('sqlite_'):  # Skip SQLite system tables
            continue
            
        schema_text += f"## Table: {table_name}\n"
        
        # Get table info
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        # Get foreign keys
        cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        foreign_keys = cursor.fetchall()
        
        # Get indexes
        cursor.execute(f"PRAGMA index_list({table_name})")
        indexes = cursor.fetchall()
        
        # Add columns
        schema_text += "### Columns:\n"
        for col in columns:
            col_id, name, type_, notnull, default_val, pk = col
            schema_text += f"- {name}: {type_}"
            if pk:
                schema_text += " PRIMARY KEY"
            if notnull:
                schema_text += " NOT NULL"
            if default_val is not None:
                schema_text += f" DEFAULT {default_val}"
            schema_text += "\n"
        
        # Add foreign keys
        if foreign_keys:
            schema_text += "\n### Foreign Keys:\n"
            for fk in foreign_keys:
                id_, seq, table, from_, to, on_update, on_delete, match = fk
                schema_text += f"- {from_} -> {table}.{to}\n"
        
        # Add indexes
        if indexes:
            schema_text += "\n### Indexes:\n"
            for idx in indexes:
                # The index_list pragma returns (seq, name, unique, origin, partial)
                seq, name, unique, origin, partial = idx
                if not name.startswith('sqlite_autoindex'):  # Skip auto-generated indexes
                    schema_text += f"- {name} (unique: {bool(unique)})\n"
        
        schema_text += "\n"
    
    # Close the connection
    conn.close()
    
    # Write to file
    with open(os.path.join(os.path.dirname(__file__), 'schema.txt'), 'w') as f:
        f.write(schema_text)

if __name__ == "__main__":
    get_schema() 