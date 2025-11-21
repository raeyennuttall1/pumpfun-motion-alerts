"""
Test script to verify system setup
"""
import sys
import os

def test_imports():
    """Test that all required packages can be imported"""
    print("Testing imports...")

    required_packages = [
        ('requests', 'requests'),
        ('websockets', 'websockets'),
        ('sqlalchemy', 'sqlalchemy'),
        ('pandas', 'pandas'),
        ('numpy', 'numpy'),
        ('torch', 'torch'),
        ('loguru', 'loguru'),
        ('yaml', 'pyyaml'),
    ]

    failed = []

    for module_name, package_name in required_packages:
        try:
            __import__(module_name)
            print(f"  ✓ {package_name}")
        except ImportError:
            print(f"  ✗ {package_name} - NOT INSTALLED")
            failed.append(package_name)

    if failed:
        print(f"\n❌ Missing packages: {', '.join(failed)}")
        print("Install with: pip install -r requirements.txt")
        return False

    print("✓ All dependencies installed\n")
    return True


def test_project_structure():
    """Test that project structure is correct"""
    print("Testing project structure...")

    required_dirs = [
        'database',
        'data_pipeline',
        'features',
        'alerts',
        'labeling',
        'analysis',
        'ml',
        'scripts'
    ]

    required_files = [
        'config.yaml',
        'requirements.txt',
        'main.py',
        'README.md'
    ]

    failed = []

    for directory in required_dirs:
        if os.path.isdir(directory):
            print(f"  ✓ {directory}/")
        else:
            print(f"  ✗ {directory}/ - MISSING")
            failed.append(directory)

    for file in required_files:
        if os.path.isfile(file):
            print(f"  ✓ {file}")
        else:
            print(f"  ✗ {file} - MISSING")
            failed.append(file)

    if failed:
        print(f"\n❌ Missing files/directories: {', '.join(failed)}")
        return False

    print("✓ Project structure correct\n")
    return True


def test_database():
    """Test database creation"""
    print("Testing database...")

    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from database.db_manager import DatabaseManager

        # Initialize database
        db = DatabaseManager(db_path="data/test.db")

        # Test basic operations
        stats = db.get_stats()
        print(f"  ✓ Database created")
        print(f"  ✓ Tables created")
        print(f"  Stats: {stats}")

        # Clean up test database
        if os.path.exists("data/test.db"):
            os.remove("data/test.db")

        print("✓ Database working\n")
        return True

    except Exception as e:
        print(f"  ✗ Database error: {e}")
        return False


def test_config():
    """Test config file"""
    print("Testing configuration...")

    try:
        import yaml

        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)

        required_sections = ['api', 'database', 'motion_alert', 'labeling', 'wallet_intelligence']

        for section in required_sections:
            if section in config:
                print(f"  ✓ {section} section")
            else:
                print(f"  ✗ {section} section - MISSING")
                return False

        print("✓ Configuration valid\n")
        return True

    except Exception as e:
        print(f"  ✗ Config error: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("PUMP.FUN MOTION ALERT SYSTEM - SETUP TEST")
    print("="*60 + "\n")

    tests = [
        ("Import Test", test_imports),
        ("Project Structure", test_project_structure),
        ("Configuration", test_config),
        ("Database", test_database),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with error: {e}\n")
            results.append((test_name, False))

    # Summary
    print("="*60)
    print("TEST SUMMARY")
    print("="*60 + "\n")

    all_passed = True
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {test_name}")
        if not result:
            all_passed = False

    print()

    if all_passed:
        print("🎉 ALL TESTS PASSED!")
        print("\nSystem is ready to use. Run: python main.py")
    else:
        print("❌ SOME TESTS FAILED")
        print("\nPlease fix the issues above before running the system.")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
