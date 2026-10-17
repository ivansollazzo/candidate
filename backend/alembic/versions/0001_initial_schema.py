"""initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-17 14:26:22.041978
"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('application',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('company', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('location', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('work_mode', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('contract_type', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('seniority', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('salary_min', sa.Integer(), nullable=True),
    sa.Column('salary_max', sa.Integer(), nullable=True),
    sa.Column('salary_currency', sa.String(length=8), nullable=True),
    sa.Column('salary_text', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('responsibilities', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('requirements', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('nice_to_have', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('benefits', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('skills', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('languages', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('education_required', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('experience_years_min', sa.Float(), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('source_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('contact_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('contact_email', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('applied_on', sa.Date(), nullable=True),
    sa.Column('next_step_on', sa.Date(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('extraction_status', sa.String(length=20), nullable=False),
    sa.Column('extraction_error', sa.Text(), nullable=True),
    sa.Column('advice', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('advice_status', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_application_status'), 'application', ['status'], unique=False)
    op.create_table('profile',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('phone', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('location', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('headline', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('years_of_experience', sa.Float(), nullable=True),
    sa.Column('skills', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('experiences', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('education', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('languages', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('certifications', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('cv_filename', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('cv_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('cv_text', sa.Text(), nullable=True),
    sa.Column('extraction_status', sa.String(length=20), nullable=True),
    sa.Column('extraction_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('application_event',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('application_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('occurred_on', sa.Date(), nullable=False),
    sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('details', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['application_id'], ['application.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_application_event_application_id'), 'application_event', ['application_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_application_event_application_id'), table_name='application_event')
    op.drop_table('application_event')
    op.drop_table('profile')
    op.drop_index(op.f('ix_application_status'), table_name='application')
    op.drop_table('application')
