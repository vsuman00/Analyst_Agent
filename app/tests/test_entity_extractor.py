import os
# Set a dummy API key before any imports to prevent EnvironmentError from app.utils.llm_client
os.environ["OPENAI_API_KEY"] = "sk-mock-key"

import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

# Now import llm_client so that mock patch can resolve the name correctly
import app.utils.llm_client
from app.eca.entity_extractor import extract_entities


class EntityExtractorTests(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for repository context
        self.test_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.test_dir)

    def tearDown(self):
        # Clean up temporary directory
        shutil.rmtree(self.test_dir)

    def test_regex_fallback_without_api_key(self):
        """
        Verify that when OPENAI_API_KEY is not set, the extractor
        uses the local deterministic regex logic on Java/Kotlin files.
        """
        # Set up a dummy Kotlin data class file
        src_dir = self.repo_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        
        kt_file = src_dir / "User.kt"
        kt_file.write_text(
            'package com.example.models\n\n'
            'data class User(val id: Long, val name: String)\n',
            encoding="utf-8"
        )
        
        # Ensure API key is missing by clearing the env dict inside the context block
        with patch.dict(os.environ, {}, clear=True):
            result = extract_entities(self.repo_path)
            
        self.assertIn("entities", result)
        entities = result["entities"]
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["name"], "User")
        self.assertEqual(entities[0]["entity_type"], "data_class")
        self.assertEqual(entities[0]["fields"], ["id", "name"])

    @patch("app.utils.llm_client.llm_json_call")
    def test_llm_parsing_with_api_key(self, mock_llm_call):
        """
        Verify that when OPENAI_API_KEY is present, the extractor calls the LLM,
        and parses generic files (like python or typescript) correctly.
        """
        # Set up a dummy Python file
        src_dir = self.repo_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        
        py_file = src_dir / "models.py"
        py_file.write_text(
            'from django.db import db\n\n'
            'class Product(db.Model):\n'
            '    name = db.CharField(max_length=100)\n'
            '    price = db.DecimalField()\n',
            encoding="utf-8"
        )
        
        # Mock LLM response to match the EntityExtractionResult Pydantic schema
        mock_llm_call.return_value = {
            "entities": [
                {
                    "name": "Product",
                    "source_file": "src/models.py",
                    "table_name": "products",
                    "fields": ["name", "price"],
                    "entity_type": "generic_model"
                }
            ]
        }
        
        # Set API key in environment for the test duration
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-mock-key"}):
            result = extract_entities(self.repo_path)
            
        self.assertIn("entities", result)
        entities = result["entities"]
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["name"], "Product")
        self.assertEqual(entities[0]["entity_type"], "generic_model")
        self.assertEqual(entities[0]["fields"], ["name", "price"])
        self.assertEqual(entities[0]["table_name"], "products")
        
        # Verify that LLM was called
        mock_llm_call.assert_called_once()

    @patch("app.utils.llm_client.llm_json_call")
    def test_llm_parsing_failure_fallback(self, mock_llm_call):
        """
        Verify that if the LLM call fails with an exception, the extractor
        gracefully falls back to the deterministic regex parser and does not crash.
        """
        # Set up a JVM file
        src_dir = self.repo_path / "src"
        src_dir.mkdir(parents=True, exist_ok=True)
        
        java_file = src_dir / "User.java"
        java_file.write_text(
            'package com.example.models;\n\n'
            '@Entity\n'
            '@Table(name = "users")\n'
            'public class User {\n'
            '    private Long id;\n'
            '    private String name;\n'
            '}\n',
            encoding="utf-8"
        )
        
        # Force LLM call to fail
        mock_llm_call.side_effect = RuntimeError("OpenAI connection failed")
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-mock-key"}):
            result = extract_entities(self.repo_path)
            
        # The result should still contain the Java entity parsed via regex fallback
        self.assertIn("entities", result)
        entities = result["entities"]
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["name"], "User")
        self.assertEqual(entities[0]["entity_type"], "jpa_entity")
        self.assertEqual(entities[0]["table_name"], "users")


if __name__ == "__main__":
    unittest.main()
