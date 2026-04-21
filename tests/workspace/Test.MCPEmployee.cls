Class Test.MCPEmployee Extends %Persistent
{

Property FullName As %String(MAXLEN = 100);

Property Address As Test.MCPAddress;

Property Salary As %Numeric(SCALE = 2);

}