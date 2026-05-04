# Graph Report - .  (2026-05-04)

## Corpus Check
- 199 files · ~217,664 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 530 nodes · 628 edges · 86 communities detected
- Extraction: 85% EXTRACTED · 15% INFERRED · 0% AMBIGUOUS · INFERRED: 94 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `OwnerControllerTest` - 13 edges
2. `AnalysisFeature` - 12 edges
3. `Requirement` - 12 edges
4. `MinimalBRD` - 12 edges
5. `ExtractedFeature` - 11 edges
6. `FeatureExtractionResult` - 11 edges
7. `ValidatedFeature` - 11 edges
8. `FeatureValidationResult` - 11 edges
9. `ProductProfile` - 10 edges
10. `ProductUnderstandingResult` - 10 edges

## Surprising Connections (you probably didn't know these)
- `brd_fix_loop.py — Layer 3 Tool -------------------------------- BRDFixLoop  Inpu` --uses--> `BRDValidationResult`  [INFERRED]
  app/analysis/brd_fix_loop.py → app/schemas/models.py
- `Apply deterministic fixes based on validation issues.` --uses--> `BRDValidationResult`  [INFERRED]
  app/analysis/brd_fix_loop.py → app/schemas/models.py
- `Run the validation/fix loop.     Returns:       {         "final_markdown": str,` --uses--> `BRDValidationResult`  [INFERRED]
  app/analysis/brd_fix_loop.py → app/schemas/models.py
- `functional_requirement_generator.py — Layer 3 Tool -----------------------------` --uses--> `FunctionalRequirement`  [INFERRED]
  app/analysis/functional_requirement_generator.py → app/schemas/models.py
- `Return (priority_label, max_fr_count) based on confidence.` --uses--> `FunctionalRequirement`  [INFERRED]
  app/analysis/functional_requirement_generator.py → app/schemas/models.py

## Communities

### Community 0 - "Basemodel"
Cohesion: 0.07
Nodes (52): BaseModel, brd_validator.py — Layer 3 Tool -------------------------------- BRDValidator  I, Evaluate the quality of a generated BRD based on strict parsing rules., validate_brd(), _build_module_index(), _content_summary(), extract_features(), _keywords_in_text() (+44 more)

### Community 1 - "Main"
Cohesion: 0.04
Nodes (42): analyze_and_convert(), AnalyzeRequest, compose_brd_endpoint(), ComposeBRDRequest, convert_payload(), ConvertRequest, extract_features_endpoint(), ExtractFeaturesRequest (+34 more)

### Community 2 - "Models Analysisfeature"
Cohesion: 0.2
Nodes (23): AnalysisFeature, MinimalBRD, A product-level feature derived deterministically from the final payload., A functional requirement derived from a detected feature or validation output., Minimal, structured BRD derived purely from the pipeline's final payload., Requirement, build_brd(), _derive_gaps() (+15 more)

### Community 3 - "Models Productprofile"
Cohesion: 0.22
Nodes (18): ProductProfile, ProductUnderstandingResult, Structured product understanding derived purely from validated features.      Ru, Top-level output envelope for ProductUnderstandingAgent., _build_summary(), _derive_capabilities(), _detect_archetype(), product_understanding_agent.py — Layer 3 Tool ---------------------------------- (+10 more)

### Community 4 - "Visualization"
Cohesion: 0.21
Nodes (15): generate_all_visualizations(), plot_clusters_3d(), plot_cumulative_variance(), plot_elbow_curve(), plot_explained_variance(), plot_pca_3d(), visualization.py - PCA & KMeans Visualization Module.  Provides 5 professional v, 3D scatter plot of the first three PCA components.          Visualizes the data (+7 more)

### Community 5 - "Ownercontrollertest"
Cohesion: 0.14
Nodes (1): OwnerControllerTest

### Community 6 - "Models Nonfunctionalrequirement"
Cohesion: 0.28
Nodes (12): NonFunctionalRequirement, NonFunctionalRequirementsResult, A single non-functional requirement inferred from system context.      Rules:, Top-level output envelope for NonFunctionalRequirementGenerator., _feature_names(), generate_nfrs(), _is_activated(), NFRCandidate (+4 more)

### Community 7 - "Utils"
Cohesion: 0.17
Nodes (11): format_currency(), format_pct(), metric_card(), utils.py - Shared utility functions for the dashboard. Formatting helpers, color, Format a float as a percentage string., Format as Indian currency (₹) with commas., Return color based on PD risk level., Return a styled badge for risk level. (+3 more)

### Community 8 - "Model Loader"
Cohesion: 0.23
Nodes (11): load_all_models(), load_ann(), load_kmeans(), load_pca(), load_scaler(), model_loader.py - Load pre-trained ML models (scaler, PCA, KMeans, ANN)., Load the fitted StandardScaler., Load the fitted PCA model. (+3 more)

### Community 9 - "Functional Requirement Generator"
Cohesion: 0.29
Nodes (10): generate_requirements(), _get_templates(), _modules_str(), _priority(), functional_requirement_generator.py — Layer 3 Tool -----------------------------, Generate 1–3 testable functional requirements per validated feature.      Parame, Return (priority_label, max_fr_count) based on confidence., _to_title() (+2 more)

### Community 10 - "Ownercontroller"
Cohesion: 0.2
Nodes (1): OwnerController

### Community 11 - "Petcontroller"
Cohesion: 0.2
Nodes (1): PetController

### Community 12 - "Petcontrollertest"
Cohesion: 0.22
Nodes (1): PetControllerTest

### Community 13 - "Data Loader"
Cohesion: 0.25
Nodes (7): load_data(), load_raw_data(), load_strategy_report(), data_loader.py - Load the business financial stress dataset from CSV. Provides a, Load the CSV dataset into a pandas DataFrame.     Prints dataset shape and basic, Load the raw 100K business financial dataset and add engineered features., Load the sector-level strategy CSV generated by the ML pipeline.

### Community 14 - "Sector Analysis"
Cohesion: 0.25
Nodes (7): analyze_sectors(), get_cluster_distribution(), get_sector_summary(), sector_analysis.py - Aggregate analysis by Business Type. Groups results by sect, Aggregate key metrics by Business_Type.      Returns DataFrame with: Count, Avg_, Aggregate risk, OD scoring, and interest strategy data by Business_Type.     Gen, Get cluster distribution per sector.

### Community 15 - "Ann Risk Model"
Cohesion: 0.32
Nodes (7): build_ann(), create_risk_label(), ann_risk_model.py - Artificial Neural Network for risk prediction.  Architecture, Create a proxy risk label for training.     A business is considered 'high risk', Build the ANN model using sklearn MLPClassifier.     Architecture: 256 → 128 → 6, Prepare features, create labels, build, and train the ANN model.          Args:, train_ann()

### Community 16 - "Brd Composer"
Cohesion: 0.33
Nodes (5): compose_brd(), brd_composer.py — Layer 3 Tool -------------------------------- BRDComposer (v0), Helper to format snake_case to Title Case if needed., Generate a Markdown BRD from the structured inputs., _to_title()

### Community 17 - "Pettypeformattertest"
Cohesion: 0.29
Nodes (1): PetTypeFormatterTest

### Community 18 - "Runner"
Cohesion: 0.4
Nodes (4): log_stage(), run_full_pipeline.py — Master Orchestration Script -----------------------------, Helper function to cleanly log pipeline stages., run_end_to_end()

### Community 19 - "Brd Fix Loop"
Cohesion: 0.4
Nodes (5): _apply_fixes(), brd_fix_loop.py — Layer 3 Tool -------------------------------- BRDFixLoop  Inpu, Apply deterministic fixes based on validation issues., Run the validation/fix loop.     Returns:       {         "final_markdown": str,, run_fix_loop()

### Community 20 - "Repo Scanner"
Cohesion: 0.47
Nodes (5): clone_repository(), is_binary(), Clones the repository and returns True if successful., Clones and scans a repository, returning metadata matching the output schema., scan_repository()

### Community 21 - "Vetcontrollertest"
Cohesion: 0.33
Nodes (1): VetControllerTest

### Community 22 - "Petrepositorytest"
Cohesion: 0.33
Nodes (1): PetRepositoryTest

### Community 23 - "Visitcontrollertest"
Cohesion: 0.33
Nodes (1): VisitControllerTest

### Community 24 - "Ownerrepositorytest"
Cohesion: 0.33
Nodes (1): OwnerRepositoryTest

### Community 25 - "Visitcontroller"
Cohesion: 0.33
Nodes (1): VisitController

### Community 26 - "Extractor"
Cohesion: 0.7
Nodes (4): build_file_tree(), classify_file(), extract_eca(), is_text_file()

### Community 27 - "Vetcontroller"
Cohesion: 0.4
Nodes (1): VetController

### Community 28 - "Vet"
Cohesion: 0.4
Nodes (1): Vet

### Community 29 - "Petrepository"
Cohesion: 0.4
Nodes (1): PetRepository

### Community 30 - "Ownerrepository"
Cohesion: 0.4
Nodes (1): OwnerRepository

### Community 31 - "Owner"
Cohesion: 0.4
Nodes (1): Owner

### Community 32 - "Aggregator"
Cohesion: 0.67
Nodes (3): aggregate_context(), determine_module_name(), Determines the module name deterministically based on folder structure.     File

### Community 33 - "Normalizer"
Cohesion: 0.67
Nodes (3): normalize_context(), Standardize a module name to snake_case format., standardize_name()

### Community 34 - "Final Output Builder"
Cohesion: 0.5
Nodes (2): build_final_output(), Combines all partial outputs into the final deterministic schema.

### Community 35 - "Simulation"
Cohesion: 0.5
Nodes (3): simulation.py - What-If Simulator engine. Allows users to input custom business, Simulate a single business through the ML pipeline.      Args:         params: D, simulate_business()

### Community 36 - "Scoring"
Cohesion: 0.5
Nodes (3): compute_risk_scores(), scoring.py - Risk scoring and OD suitability computation. Uses loaded models to, Run the full scoring pipeline on a DataFrame:       Scale → PCA → Cluster → ANN

### Community 37 - "Styles"
Cohesion: 0.5
Nodes (3): inject_custom_css(), styles.py - Glassmorphism CSS theme for the Credit Intelligence Dashboard. Provi, Inject the full glassmorphism CSS into the current Streamlit page.

### Community 38 - "Scaling"
Cohesion: 0.5
Nodes (3): scaling.py - Feature scaling using StandardScaler. Standardizes features: X_scal, Apply StandardScaler to the selected numeric features.     Saves the fitted scal, scale_features()

### Community 39 - "Feature Engineering"
Cohesion: 0.5
Nodes (3): engineer_features(), feature_engineering.py - Create derived features as per PRD.  Engineered Feature, Create new features from existing columns.          Args:         df: Preprocess

### Community 40 - "Clustering"
Cohesion: 0.5
Nodes (3): apply_clustering(), clustering.py - K-Means clustering for business behavior segmentation. Segments, Apply K-Means clustering on PCA-transformed data.          Args:         X_pca:

### Community 41 - "Interest Strategy"
Cohesion: 0.5
Nodes (3): apply_interest_strategy(), interest_strategy.py - Interest rate reduction strategy.  Rule (per PRD):     Re, Flag businesses eligible for interest rate reduction.          Criteria:

### Community 42 - "Pca Module"
Cohesion: 0.5
Nodes (3): apply_pca(), pca_module.py - Principal Component Analysis for dimensionality reduction. Retai, Apply PCA to the scaled feature matrix.     Retains components that explain >= 9

### Community 43 - "Evaluation"
Cohesion: 0.5
Nodes (3): evaluate_model(), evaluation.py - Model evaluation metrics. Computes AUC-ROC, classification repor, Evaluate the trained ANN model on the test set.          Args:         model: Tr

### Community 44 - "Preprocessing"
Cohesion: 0.5
Nodes (3): preprocess_data(), preprocessing.py - Data cleaning and preprocessing. Handles missing values, dupl, Clean and preprocess the raw dataset.          Steps:         1. Drop duplicate

### Community 45 - "Pipeline"
Cohesion: 0.5
Nodes (3): pipeline.py - End-to-end ML pipeline orchestrator.  Flow (per PRD):     Load Dat, Execute the full Intelligent OD System pipeline.          Returns:         dict:, run_pipeline()

### Community 46 - "Od Scoring"
Cohesion: 0.5
Nodes (3): compute_od_score(), od_scoring.py - OD Suitability Scoring.  Formula (per PRD):     ODScore = (1 - P, Calculate the OD suitability score for each business.          Args:         df:

### Community 47 - "Visitrepositorytest"
Cohesion: 0.5
Nodes (1): VisitRepositoryTest

### Community 48 - "Validatortests"
Cohesion: 0.5
Nodes (1): ValidatorTests

### Community 49 - "Pettypeformatter"
Cohesion: 0.5
Nodes (1): PetTypeFormatter

### Community 50 - "Pet"
Cohesion: 0.5
Nodes (1): Pet

### Community 51 - "Petvalidator"
Cohesion: 0.5
Nodes (1): PetValidator

### Community 52 - "Visitrepository"
Cohesion: 0.5
Nodes (1): VisitRepository

### Community 53 - "Cacheconfig"
Cohesion: 0.5
Nodes (1): CacheConfig

### Community 54 - "Test Pipeline"
Cohesion: 1.0
Nodes (2): run_pipeline(), setup_dummy_repo()

### Community 55 - "Content Processor"
Cohesion: 1.0
Nodes (2): process_file(), run_content_processor()

### Community 56 - "File Classifier"
Cohesion: 1.0
Nodes (2): classify_file(), run_classifier()

### Community 57 - "Petclinicintegrationtests"
Cohesion: 0.67
Nodes (1): PetclinicIntegrationTests

### Community 58 - "Vetrepositorytest"
Cohesion: 0.67
Nodes (1): VetRepositoryTest

### Community 59 - "Vettest"
Cohesion: 0.67
Nodes (1): VetTest

### Community 60 - "Mockmvcvalidationconfiguration"
Cohesion: 0.67
Nodes (1): MockMvcValidationConfiguration

### Community 61 - "Crashcontrollertest"
Cohesion: 0.67
Nodes (1): CrashControllerTest

### Community 62 - "Petclinicapplication"
Cohesion: 0.67
Nodes (1): PetClinicApplication

### Community 63 - "Vetrepository"
Cohesion: 0.67
Nodes (1): VetRepository

### Community 64 - "Crashcontroller"
Cohesion: 0.67
Nodes (1): CrashController

### Community 65 - "Welcomecontroller"
Cohesion: 0.67
Nodes (1): WelcomeController

### Community 66 - "Namedentity"
Cohesion: 0.67
Nodes (1): NamedEntity

### Community 67 - "Validator"
Cohesion: 1.0
Nodes (0): 

### Community 68 - "Builder"
Cohesion: 1.0
Nodes (0): 

### Community 69 - "Config"
Cohesion: 1.0
Nodes (1): config.py - Configuration for the Credit Intelligence Dashboard. Points to ML pi

### Community 70 - "App"
Cohesion: 1.0
Nodes (1): app.py - Main entry point for the Credit Intelligence Dashboard. Streamlit multi

### Community 71 - "1 Executive Summary"
Cohesion: 1.0
Nodes (1): 1_Executive_Summary.py - High-level KPI dashboard with glassmorphism design.

### Community 72 - "4 Od Optimization"
Cohesion: 1.0
Nodes (1): 4_OD_Optimization.py - OD suitability analysis with glassmorphism design.

### Community 73 - "5 Interest Strategy"
Cohesion: 1.0
Nodes (1): 5_Interest_Strategy.py - Interest rate reduction strategy with glassmorphism des

### Community 74 - "3 Cluster Insights"
Cohesion: 1.0
Nodes (1): 3_Cluster_Insights.py - K-Means cluster profiling with glassmorphism design.

### Community 75 - "6 What If"
Cohesion: 1.0
Nodes (1): 6_What_If_Simulator.py - Interactive simulator with glassmorphism design.

### Community 76 - "2 Risk Analysis"
Cohesion: 1.0
Nodes (1): 2_Risk_Analysis.py - Risk analysis with glassmorphism design.

### Community 77 - "Vets"
Cohesion: 1.0
Nodes (1): Vets

### Community 78 - "Specialty"
Cohesion: 1.0
Nodes (1): Specialty

### Community 79 - "Pettype"
Cohesion: 1.0
Nodes (1): PetType

### Community 80 - "Visit"
Cohesion: 1.0
Nodes (1): Visit

### Community 81 - "Baseentity"
Cohesion: 1.0
Nodes (1): BaseEntity

### Community 82 - "Person"
Cohesion: 1.0
Nodes (1): Person

### Community 83 - "Init"
Cohesion: 1.0
Nodes (0): 

### Community 84 - "Build Gradle"
Cohesion: 1.0
Nodes (0): 

### Community 85 - "Settings Gradle"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **116 isolated node(s):** `run_full_pipeline.py — Master Orchestration Script -----------------------------`, `Helper function to cleanly log pipeline stages.`, `Determines the module name deterministically based on folder structure.     File`, `Standardize a module name to snake_case format.`, `brd_composer.py — Layer 3 Tool -------------------------------- BRDComposer (v0)` (+111 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Validator`** (2 nodes): `validator.py`, `validate_context()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Builder`** (2 nodes): `builder.py`, `analyze_context()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Config`** (2 nodes): `config.py`, `config.py - Configuration for the Credit Intelligence Dashboard. Points to ML pi`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `App`** (2 nodes): `app.py`, `app.py - Main entry point for the Credit Intelligence Dashboard. Streamlit multi`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `1 Executive Summary`** (2 nodes): `1_Executive_Summary.py`, `1_Executive_Summary.py - High-level KPI dashboard with glassmorphism design.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `4 Od Optimization`** (2 nodes): `4_OD_Optimization.py`, `4_OD_Optimization.py - OD suitability analysis with glassmorphism design.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `5 Interest Strategy`** (2 nodes): `5_Interest_Strategy.py`, `5_Interest_Strategy.py - Interest rate reduction strategy with glassmorphism des`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `3 Cluster Insights`** (2 nodes): `3_Cluster_Insights.py`, `3_Cluster_Insights.py - K-Means cluster profiling with glassmorphism design.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `6 What If`** (2 nodes): `6_What_If_Simulator.py`, `6_What_If_Simulator.py - Interactive simulator with glassmorphism design.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `2 Risk Analysis`** (2 nodes): `2_Risk_Analysis.py`, `2_Risk_Analysis.py - Risk analysis with glassmorphism design.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Vets`** (2 nodes): `Vets.kt`, `Vets`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Specialty`** (2 nodes): `Specialty.kt`, `Specialty`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Pettype`** (2 nodes): `PetType.kt`, `PetType`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Visit`** (2 nodes): `Visit.kt`, `Visit`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Baseentity`** (2 nodes): `BaseEntity.kt`, `BaseEntity`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Person`** (2 nodes): `Person.kt`, `Person`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Build Gradle`** (1 nodes): `build.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Settings Gradle`** (1 nodes): `settings.gradle.kts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `BRDValidationResult` connect `Basemodel` to `Brd Fix Loop`?**
  _High betweenness centrality (0.013) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `AnalysisFeature` (e.g. with `payload_converter.py — Layer 3 Tool ------------------------------------- Conver` and `Infer a feature category from its source file paths deterministically.`) actually correct?**
  _`AnalysisFeature` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `Requirement` (e.g. with `payload_converter.py — Layer 3 Tool ------------------------------------- Conver` and `Infer a feature category from its source file paths deterministically.`) actually correct?**
  _`Requirement` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `MinimalBRD` (e.g. with `payload_converter.py — Layer 3 Tool ------------------------------------- Conver` and `Infer a feature category from its source file paths deterministically.`) actually correct?**
  _`MinimalBRD` has 9 INFERRED edges - model-reasoned connections that need verification._
- **What connects `run_full_pipeline.py — Master Orchestration Script -----------------------------`, `Helper function to cleanly log pipeline stages.`, `Determines the module name deterministically based on folder structure.     File` to the rest of the system?**
  _116 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Basemodel` be split into smaller, more focused modules?**
  _Cohesion score 0.07 - nodes in this community are weakly interconnected._
- **Should `Main` be split into smaller, more focused modules?**
  _Cohesion score 0.04 - nodes in this community are weakly interconnected._